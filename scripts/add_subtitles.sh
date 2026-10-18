#!/usr/bin/env bash
# add_subtitles.sh —— 视频自动加字幕并烧录
# 流程：抽音轨 -> whisper.cpp 转录出 SRT -> SRT 转 ASS -> libass 烧录进画面
# 依赖：带 libass 的 ffmpeg、whisper-cli、ggml 模型、python3（详见 README.md）
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

VIDEO=""
OUT=""
LANG_OPT="zh"
FONTSIZE=42
SRT_ONLY=0

# ---- 解析参数 ----
while [ $# -gt 0 ]; do
  case "$1" in
    -o|--output)   OUT="$2"; shift 2 ;;
    -l|--language) LANG_OPT="$2"; shift 2 ;;
    -f|--fontsize) FONTSIZE="$2"; shift 2 ;;
    -s|--srt-only) SRT_ONLY=1; shift ;;
    -h|--help)
      echo "用法: add_subtitles.sh <视频路径> [-o 输出.mp4] [-l 语言] [-f 字号] [-s 只出字幕]"
      exit 0 ;;
    -*) echo "未知参数: $1" >&2; exit 2 ;;
    *)  VIDEO="$1"; shift ;;
  esac
done

[ -n "$VIDEO" ] || { echo "用法: add_subtitles.sh <视频路径> [-o 输出.mp4] [-l 语言] [-f 字号] [-s 只出字幕]" >&2; exit 2; }
[ -f "$VIDEO" ] || { echo "找不到视频文件: $VIDEO" >&2; exit 2; }
[ -n "$OUT" ] || OUT="${VIDEO%.*}_subtitled.mp4"

# ---- 1. 找一个带 libass 的 ffmpeg ----
# Homebrew 的精简 ffmpeg 没有 libass，必须检查 subtitles 滤镜是否存在
has_subtitles_filter() {
  "$1" -hide_banner -filters 2>/dev/null | awk '{print $2}' | grep -qx "subtitles"
}
FFMPEG_BIN=""
for cand in "${FFMPEG:-}" "$HOME/.local/bin/ffmpeg-libass" "$(command -v ffmpeg || true)" \
            /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg /opt/homebrew/bin/ffmpeg; do
  if [ -n "$cand" ] && [ -x "$cand" ] && has_subtitles_filter "$cand"; then
    FFMPEG_BIN="$cand"; break
  fi
done
if [ -z "$FFMPEG_BIN" ]; then
  cat >&2 <<'EOF'
错误：没有找到带 libass 的 ffmpeg（缺少 subtitles/ass 滤镜）。
安装方式见 skill 的 README.md；也可用 FFMPEG=/path/to/ffmpeg 指定。
EOF
  exit 1
fi

# ---- 2. whisper.cpp 与模型 ----
WHISPER_CLI="${WHISPER_CLI:-$(command -v whisper-cli || true)}"
[ -n "$WHISPER_CLI" ] && [ -x "$WHISPER_CLI" ] || WHISPER_CLI=/opt/homebrew/bin/whisper-cli
[ -x "$WHISPER_CLI" ] || { echo "错误：缺少 whisper-cli，请执行 brew install whisper-cpp" >&2; exit 1; }

MODEL="${WHISPER_MODEL:-}"
if [ -z "$MODEL" ]; then
  for cand in "$HOME/.cache/whisper/ggml-large-v3.bin" \
              "$HOME/.cache/whisper/ggml-medium.bin" \
              "$HOME/.cache/whisper/ggml-small.bin" \
              "$HOME/.cache/whisper.cpp/ggml-large-v3.bin" \
              /opt/homebrew/share/whisper.cpp/models/ggml-large-v3.bin; do
    [ -f "$cand" ] && { MODEL="$cand"; break; }
  done
fi
[ -n "$MODEL" ] && [ -f "$MODEL" ] || { echo "错误：缺少 ggml 模型，用 WHISPER_MODEL=... 指定，见 README.md" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "[1/4] 抽取音轨（ffmpeg: ${FFMPEG_BIN}）"
"$FFMPEG_BIN" -y -v error -i "$VIDEO" -vn -ac 1 -ar 16000 -c:a pcm_s16le "$WORK/audio.wav"

echo "[2/4] Whisper 转录（模型: $(basename "$MODEL")，语言: ${LANG_OPT}）"
if ! "$WHISPER_CLI" -m "$MODEL" -f "$WORK/audio.wav" -l "$LANG_OPT" \
      -osrt -of "$WORK/trans" -t "$(sysctl -n hw.ncpu)" >"$WORK/whisper.log" 2>&1; then
  cat "$WORK/whisper.log" >&2
  echo "错误：Whisper 转录失败" >&2
  exit 1
fi
[ -f "$WORK/trans.srt" ] || { echo "错误：Whisper 未产出 SRT" >&2; exit 1; }

# 把字幕内容打印出来，方便校对专有名词错字
echo "----- 转录结果 -----"
cat "$WORK/trans.srt"
echo "--------------------"

SRT_OUT="${OUT%.*}.srt"
[ "$SRT_ONLY" -eq 1 ] && SRT_OUT="${VIDEO%.*}.srt"
cp "$WORK/trans.srt" "$SRT_OUT"
echo "字幕已保存: $SRT_OUT"
[ "$SRT_ONLY" -eq 1 ] && exit 0

# ---- 3. SRT 转 ASS（按画面尺寸自动断行）----
# 从 ffmpeg 输出里抓 WxH
DIM="$("$FFMPEG_BIN" -hide_banner -i "$VIDEO" 2>&1 | grep -o -E '[0-9]{2,5}x[0-9]{2,5}' | head -1 || true)"
WIDTH="${DIM%x*}"; HEIGHT="${DIM#*x}"
[ -n "$WIDTH" ] && [ -n "$HEIGHT" ] || { echo "错误：无法获取视频分辨率" >&2; exit 1; }

echo "[3/4] 生成 ASS（${WIDTH}x${HEIGHT}，字号 ${FONTSIZE}）"
python3 "$SKILL_DIR/scripts/srt_to_ass.py" --srt "$WORK/trans.srt" --out "$WORK/final.ass" \
  --width "$WIDTH" --height "$HEIGHT" --fontsize "$FONTSIZE"

# ---- 4. 烧录 ----
echo "[4/4] 烧录字幕 -> $OUT"
"$FFMPEG_BIN" -y -v error -i "$VIDEO" -vf "ass=$WORK/final.ass" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a copy -movflags +faststart "$OUT"

echo "完成: $OUT"
echo "提示：抽 2-3 帧检查字幕有没有被裁切 -> ffmpeg -ss 5 -i \"$OUT\" -frames:v 1 check.png"

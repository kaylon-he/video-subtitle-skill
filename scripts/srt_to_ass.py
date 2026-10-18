#!/usr/bin/env python3
r"""
srt_to_ass.py —— 把 SRT 字幕转成 ASS，用于烧录进视频。

特性：
1. 按「画面宽度 / 字号」自动计算每行字数，用 \N 硬断行（ASS WrapStyle=2 不自动换行）。
2. 断行优先落在中文标点之后，避免把词语切成两半。
3. 自动挑选系统里真实存在的中文字体（macOS 上 PingFang 常不在 /System/Library/Fonts，会回退到冬青黑体）。
4. 样式：白字 + 半透明黑色底框（BorderStyle=3）+ 底部居中。

用法：
    python3 srt_to_ass.py --srt in.srt --out out.ass --fontsize 42 --width 720 --height 1280
仅使用 Python 标准库。
"""

import argparse
import os
import re
import sys

# 断行时允许「断在标点之后」的字符集合（含半角，whisper 输出常混用半角标点）
BREAK_CHARS = "，。！？；：、）】》”" + ",.!?;:"

# 候选中文（CJK）字体，按优先级排列：文件路径 -> ASS 里使用的字体名
FONT_CANDIDATES = [
    ("/System/Library/Fonts/PingFang.ttc", "PingFang SC"),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", "Hiragino Sans GB"),
    ("/System/Library/Fonts/STHeiti Medium.ttc", "STHeiti"),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", "Songti SC"),
]

# SRT 时间轴：00:00:01,234 --> 00:00:05,678（毫秒分隔符逗号或点都接受）
TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{fontsize},&H00FFFFFF,&H000000FF,&H40000000,&H00000000,0,0,0,0,100,100,0,0,3,1,2,2,{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def detect_font():
    """返回系统上第一个真实存在的中文字体名；都没有则退回 Arial。"""
    for path, name in FONT_CANDIDATES:
        if os.path.exists(path):
            return name
    return "Arial"


def has_cjk(text):
    """文本里是否含中日韩表意文字（决定多行拼接要不要加空格）。"""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def to_ass_time(h, m, s, ms):
    """SRT 的 时/分/秒/毫秒 转 ASS 的 H:MM:SS.cc（百分之一秒）。"""
    cs = int(ms) // 10
    return "%d:%02d:%02d.%02d" % (int(h), int(m), int(s), cs)


def wrap_text(text, max_chars):
    """把一句话断成多行：优先断在标点之后，同时避免溢出画面、避免末行只剩一两个字。

    规则：
    1. 长度不超过 max_chars + 1 时不换行（这个宽度仍在画面内）。
    2. 超长时在 [max_chars/2, max_chars + 1] 区间找「最后一个标点」，断在标点之后。
    3. 区间内没有标点：剩余内容不足两行就对半断，否则按上限硬断。
    """
    lines = []
    i, n = 0, len(text)
    while i < n:
        remain = n - i
        if remain <= max_chars + 1:
            lines.append(text[i:])
            break
        limit = i + max_chars
        cut = -1
        for j in range(limit + 1, i + max_chars // 2 - 1, -1):
            if j < n and text[j] in BREAK_CHARS:
                cut = j + 1
                break
        if cut <= i:
            cut = i + (remain + 1) // 2 if remain <= 2 * max_chars else limit
        lines.append(text[i:cut])
        i = cut
    return lines or [""]


def parse_srt(path):
    """解析 SRT，返回 [(开始, 结束, 文本), ...]。"""
    with open(path, "r", encoding="utf-8-sig") as fh:
        raw = fh.read()

    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        # 第一行可能是序号，找到时间轴行
        idx = 0
        if not TIME_RE.search(lines[0]) and idx + 1 < len(lines):
            idx = 1
        m = TIME_RE.search(lines[idx])
        if not m:
            continue
        start = to_ass_time(*m.group(1, 2, 3, 4))
        end = to_ass_time(*m.group(5, 6, 7, 8))
        body = lines[idx + 1 :]
        # 中文直接拼接，拉丁文用空格拼接
        text = ("" if has_cjk("".join(body)) else " ").join(body)
        text = text.replace("\\N", "").replace("-->", "->").strip()
        if text:
            cues.append((start, end, text))
    return cues


def build_ass(cues, width, height, fontsize, margin_lr, margin_v, font):
    """生成 ASS 文本：按宽度算每行字数，逐句断行。"""
    max_chars = max(4, int((width - 2 * margin_lr) / fontsize))
    out = [HEADER.format(
        width=width, height=height, fontsize=fontsize,
        ml=margin_lr, mr=margin_lr, mv=margin_v, font=font,
    )]
    for start, end, text in cues:
        wrapped = "\\N".join(wrap_text(text, max_chars))
        out.append(
            "Dialogue: 0,%s,%s,Default,,0,0,0,,%s\n" % (start, end, wrapped)
        )
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description="SRT 转 ASS（CJK 友好、宽度自适应断行）")
    ap.add_argument("--srt", required=True, help="输入 SRT 路径")
    ap.add_argument("--out", required=True, help="输出 ASS 路径")
    ap.add_argument("--width", type=int, default=720, help="画面宽（PlayResX）")
    ap.add_argument("--height", type=int, default=1280, help="画面高（PlayResY）")
    ap.add_argument("--fontsize", type=int, default=42, help="字号")
    ap.add_argument("--margin-lr", type=int, default=30, help="左右边距")
    ap.add_argument("--margin-v", type=int, default=70, help="底边距")
    ap.add_argument("--font", default="auto", help="字体名，auto 表示自动探测系统中文字体")
    args = ap.parse_args()

    font = detect_font() if args.font == "auto" else args.font
    cues = parse_srt(args.srt)
    if not cues:
        print("没有从 %s 解析到字幕" % args.srt, file=sys.stderr)
        return 1

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(build_ass(
            cues, args.width, args.height, args.fontsize,
            args.margin_lr, args.margin_v, font,
        ))
    print("已生成 %s（%d 条字幕，字体 %s）" % (args.out, len(cues), font))
    return 0


if __name__ == "__main__":
    sys.exit(main())

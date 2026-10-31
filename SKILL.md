---
name: video-subtitle
description: Add auto-generated hard subtitles to a video and output a subtitled MP4 plus SRT, with optional bilingual subtitles and static watermark removal. Use when the user asks to caption or subtitle a video, or to remove a watermark from a video.
---

# Video Subtitle

给视频自动加字幕并把字烧进画面，产出「带字幕 MP4 + SRT」。

## 流水线

1. 抽取 16k 单声道 wav（ffmpeg）
2. whisper.cpp 转录出 SRT（whisper-cli）
3. SRT → ASS：按画面宽度自动断行、CJK 字体、底部居中半透明底框
4. 用带 libass 的 ffmpeg 烧录 ASS，音轨直接 copy

## 用法

```bash
bash scripts/add_subtitles.sh input.mp4 -o output.mp4 -l zh
bash scripts/add_subtitles.sh input.mp4 -o output.mp4 -l zh -e en.srt   # 中上/英下双语
bash scripts/add_subtitles.sh input.mp4 -o output.mp4 -l en -w 1545,72,200,88   # 同时去水印
```

- `-l/--language` 源语言，默认 `zh`，可传 `auto`
- `-f/--fontsize` 字号，默认 42
- `-e/--en` 次语言 SRT，与主 SRT 按序号对齐，输出双语字幕
- `-w/--delogo` 静态水印的矩形区域 `x,y,w,h`（像素）
- `-s/--srt-only` 只出 SRT，不烧录

## 必须遵守

- **先看转录文本再交付**：脚本会把 SRT 打印到终端。人名、地名、成语常被识别错（例：「重阳姐」→「重阳节」、「久久重扬」→「九九重阳」）。有错就用 `-s` 重新出一版，改好 SRT 再烧录。
- **校验成品**：从成片抽 2–3 帧（`-ss <秒> -frames:v 1`）确认字幕完整、没有被裁切或溢出画面。
- **不要用 Homebrew 的精简 `ffmpeg`**：该构建没有 libass，`subtitles`/`ass`/`drawtext` 滤镜全部缺失。脚本会自动挑选带 libass 的 ffmpeg，装法见 README.md。
- 长句必须断行：ASS 用 `WrapStyle: 2`（只认 `\N`），`srt_to_ass.py` 已按 `画面宽度 / 字号` 自动插入 `\N`。若某句仍溢出，调小 `-f` 字号。
- **去水印要先量坐标**：截一帧放大定位（`crop=400:300:1424:0,scale=1200:-2`，图上坐标除以放大倍数再加裁剪偏移），框比字形四周各留 5–10px 再交给 `-w`。只上 `delogo` 会留竖条纹，脚本已配局部模糊补掉。
- **音频质量差的片子，ASR 会给出语义不通的句子**（例：`Penis activated` 这种明显不成立的词）。这类结果不能直接烧进成片：要么换更大模型复核，要么明确告诉用户「这是推断」并给出可替换的 SRT。

## 环境依赖

ffmpeg（带 libass）+ whisper-cli + ggml 模型 + python3。缺失时脚本会给出明确报错。完整库清单、安装命令与排错说明见 [README.md](README.md)。

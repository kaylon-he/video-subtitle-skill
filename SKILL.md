---
name: video-subtitle
description: Add auto-generated hard subtitles to a video file or URL and output a subtitled MP4 plus SRT. Use when the user asks to caption or subtitle a video. Do not use for editing existing subtitles only.
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
```

- `-l/--language` 源语言，默认 `zh`，可传 `auto`
- `-f/--fontsize` 字号，默认 42
- `-s/--srt-only` 只出 SRT，不烧录

## 必须遵守

- **先看转录文本再交付**：脚本会把 SRT 打印到终端。人名、地名、成语常被识别错（例：「重阳姐」→「重阳节」、「久久重扬」→「九九重阳」）。有错就用 `-s` 重新出一版，改好 SRT 再烧录。
- **校验成品**：从成片抽 2–3 帧（`-ss <秒> -frames:v 1`）确认字幕完整、没有被裁切或溢出画面。
- **不要用 Homebrew 的精简 `ffmpeg`**：该构建没有 libass，`subtitles`/`ass`/`drawtext` 滤镜全部缺失。脚本会自动挑选带 libass 的 ffmpeg，装法见 README.md。
- 长句必须断行：ASS 用 `WrapStyle: 2`（只认 `\N`），`srt_to_ass.py` 已按 `画面宽度 / 字号` 自动插入 `\N`。若某句仍溢出，调小 `-f` 字号。

## 环境依赖

ffmpeg（带 libass）+ whisper-cli + ggml 模型 + python3。缺失时脚本会给出明确报错。完整库清单、安装命令与排错说明见 [README.md](README.md)。

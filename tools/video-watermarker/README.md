# video-watermarker

Overlays image logos or text captions onto video files at specified positions (top-left, top-right, bottom-left, bottom-right, center) using FFmpeg.

## Usage

### Overlay Image Logo Watermark
```bash
python tools/video-watermarker/video_watermarker.py video.mp4 -w logo.png -p bottom-right
```

### Overlay Text Caption Watermark
```bash
python tools/video-watermarker/video_watermarker.py videos/ -t "Confidential" -p top-left --size 32
```

## Options
- `-w`, `--watermark`: Path to watermark PNG/JPG image logo file.
- `-t`, `--text`: Watermark text string.
- `-p`, `--position`: Position (`top-left`, `top-right`, `bottom-left`, `bottom-right`, `center`, default: `bottom-right`).
- `--size`: Text font size in points (default: `24`).
- `-o`, `--output`: Destination directory or file path.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `ffmpeg` binary on system PATH.

## Quality
Quality: pylint 10.00/10 · 83% coverage · 0 dependencies

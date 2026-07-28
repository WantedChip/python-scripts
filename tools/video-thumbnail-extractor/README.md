# video-thumbnail-extractor

Extracts high-resolution thumbnail images (JPG, PNG, WebP) at specified timestamps from video files using FFmpeg.

## Usage

### Extract Frame at 5-second mark
```bash
python tools/video-thumbnail-extractor/video_thumbnail_extractor.py video.mp4 -ss 00:00:05 -f png
```

### Batch Extract Resized Thumbnails (640px width)
```bash
python tools/video-thumbnail-extractor/video_thumbnail_extractor.py videos/ -o thumbnails/ -w 640
```

## Options
- `-ss`, `--time`: Timestamp position (`HH:MM:SS` or seconds, default: `00:00:01`).
- `-w`, `--width`: Thumbnail width in pixels.
- `-f`, `--format`: Image format (`jpg`, `png`, `webp`, default: `jpg`).
- `-o`, `--output`: Destination directory or image file path.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `ffmpeg` binary on system PATH.

## Quality
Quality: pylint 10.00/10 · 84% coverage · 0 dependencies

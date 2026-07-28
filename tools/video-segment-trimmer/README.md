# video-segment-trimmer

Trims video files to specified start and end timestamps (`HH:MM:SS` or seconds) using fast FFmpeg stream copying or frame-accurate re-encoding.

## Usage

### Fast Stream Copy Trim
```bash
python tools/video-segment-trimmer/video_segment_trimmer.py video.mp4 -ss 00:01:30 -to 00:03:00 -o output/
```

### Trim Specific Duration
```bash
python tools/video-segment-trimmer/video_segment_trimmer.py video.mp4 -ss 00:00:10 -t 45 --reencode
```

## Options
- `-ss`, `--start`: Start timestamp (`HH:MM:SS` or seconds, default: `00:00:00`).
- `-to`, `--end`: End timestamp (`HH:MM:SS` or seconds).
- `-t`, `--duration`: Segment duration in seconds or `HH:MM:SS`.
- `--reencode`: Re-encode stream for frame accuracy instead of fast copy.
- `-o`, `--output`: Destination directory or file path.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `ffmpeg` binary on system PATH.

## Quality
Quality: pylint 10.00/10 · 89% coverage · 0 dependencies

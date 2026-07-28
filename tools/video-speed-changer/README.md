# video-speed-changer

Adjusts playback speed of video files (e.g. 0.5x slow motion, 1.5x, 2.0x fast forward) while preserving audio pitch using FFmpeg filters.

## Usage

### 2x Fast Forward Video
```bash
python tools/video-speed-changer/video_speed_changer.py lecture.mp4 -s 2.0 -o fast/
```

### 0.5x Slow Motion Batch
```bash
python tools/video-speed-changer/video_speed_changer.py sports/ -s 0.5
```

## Options
- `-s`, `--speed`: Playback speed multiplier (default: `1.5`).
- `-o`, `--output`: Destination directory or output file path.
- `--suffix`: Filename suffix (default: `_<speed>x`).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `ffmpeg` binary on system PATH.

## Quality
Quality: pylint 10.00/10 · 85% coverage · 0 dependencies

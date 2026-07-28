# video-resolution-converter

Converts videos to standard target resolutions (`360p`, `480p`, `720p`, `1080p`, `4k`) in batch while maintaining aspect ratios using FFmpeg scaling.

## Usage

### Convert to 720p Resolution
```bash
python converters/video-resolution-converter/video_resolution_converter.py video.mp4 -r 720p -o converted/
```

### Batch Convert to 480p with Quality Control
```bash
python converters/video-resolution-converter/video_resolution_converter.py videos/ -r 480p --crf 20
```

## Options
- `-r`, `--resolution`: Target resolution (`360p`, `480p`, `720p`, `1080p`, `4k`, default: `720p`).
- `--crf`: x264 Constant Rate Factor quality rating 0-51 (default: 23).
- `-o`, `--output`: Destination directory.
- `--suffix`: Filename suffix (default: `_<resolution>`).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `ffmpeg` binary on system PATH.

## Quality
Quality: pylint 10.00/10 · 88% coverage · 0 dependencies

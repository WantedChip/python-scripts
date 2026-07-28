# audio-volume-normalizer

Normalizes audio volume levels to a target LUFS loudness level (via FFmpeg) or peak scale factor (natively for 16-bit WAV files).

## Usage

### Native WAV Peak Normalization
```bash
python tools/audio-volume-normalizer/audio_volume_normalizer.py music.wav -p 0.95
```

### FFmpeg LUFS Volume Normalization
```bash
python tools/audio-volume-normalizer/audio_volume_normalizer.py tracks/ -o normalized/ -l -14.0
```

## Options
- `-l`, `--lufs`: Target integrated LUFS loudness level for FFmpeg (default: `-14.0`).
- `-p`, `--peak`: Target peak scale factor for native WAV mode (default: `0.95`).
- `-o`, `--output`: Destination directory.
- `--suffix`: Filename suffix (default: `_norm`).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- Standard Library (`wave`, `struct`, `math`) for native WAV files.
- `ffmpeg` on PATH for MP3, FLAC, AAC, or LUFS mode.

## Quality
Quality: pylint 10.00/10 · 84% coverage · 0 dependencies

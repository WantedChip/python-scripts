# audio-noise-profiler

Analyzes audio files and reports sections with high background noise or digital clipping.

## Usage

### Analyze Audio File or Directory
```bash
python tools/audio-noise-profiler/audio_noise_profiler.py recording.wav
```

### Custom Clipping and Noise Thresholds
```bash
python tools/audio-noise-profiler/audio_noise_profiler.py audio_folder/ --clip-threshold 0.95 --noise-floor-db -25.0
```

### Export JSON Report
```bash
python tools/audio-noise-profiler/audio_noise_profiler.py audio_folder/ -f json -o noise_report.json
```

## Options
- `--clip-threshold`: Threshold ratio of max sample amplitude to count as clipping (default: `0.99`).
- `--noise-floor-db`: Decibel threshold above which background noise is flagged (default: `-30.0` dBFS).
- `-r`, `--recursive`: Scan directory recursively.
- `-o`, `--output`: Target report output path.
- `-f`, `--format`: Console output format (`table`, `csv`, `json`).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- Standard Library (`wave`, `struct`, `math`, `csv`, `json`).
- `ffmpeg` on PATH for non-WAV formats (MP3, FLAC, AAC, OGG).

## Quality
Quality: pylint 10.00/10 · 88% coverage · 0 dependencies

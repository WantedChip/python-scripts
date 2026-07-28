# podcast-audio-splitter

Splits long audio recordings or podcast episodes into chapter files using silence boundary detection.

## Usage

### Native WAV Podcast Chapter Splitting
```bash
python tools/podcast-audio-splitter/podcast_audio_splitter.py episode.wav -s 1.5 -o chapters/
```

### FFmpeg MP3/FLAC Chapter Splitting
```bash
python tools/podcast-audio-splitter/podcast_audio_splitter.py interview.mp3 -s 2.0 -p "section_"
```

## Options
- `-s`, `--silence`: Minimum silence duration in seconds to trigger split (default: `1.5`).
- `-p`, `--prefix`: Filename prefix for chapter files (default: `chapter_`).
- `-o`, `--output`: Target output directory for chapter files.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- Standard Library (`wave`, `struct`) for native 16-bit WAV files.
- `ffmpeg` on PATH for MP3, AAC, FLAC, or OGG recordings.

## Quality
Quality: pylint 10.00/10 · 83% coverage · 0 dependencies

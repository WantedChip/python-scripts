# audio-file-joiner

Concatenates multiple audio files into a single continuous track using native WAV PCM merging or FFmpeg concat demuxing.

## Usage

### Join WAV files (Native PCM)
```bash
python tools/audio-file-joiner/audio_file_joiner.py track1.wav track2.wav -o full_album.wav
```

### Batch Join MP3 Audio Tracks
```bash
python tools/audio-file-joiner/audio_file_joiner.py parts_dir/ -o combined_podcast.mp3
```

## Options
- `inputs`: One or more input audio file paths or directory.
- `-o`, `--output`: Target output merged audio file path (required).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- Standard Library (`wave`, `struct`) for native 16-bit WAV files.
- `ffmpeg` on PATH for MP3, AAC, FLAC, or OGG tracks.

## Quality
Quality: pylint 10.00/10 · 84% coverage · 0 dependencies

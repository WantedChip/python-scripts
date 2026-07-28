# audio-format-converter

Converts audio files between MP3, WAV, FLAC, OGG, and AAC formats in bulk using FFmpeg.

## Usage

### Convert WAV to MP3 (192k)
```bash
python converters/audio-format-converter/audio_format_converter.py song.wav -f mp3 -b 320k
```

### Batch Convert FLAC files to WAV
```bash
python converters/audio-format-converter/audio_format_converter.py library/ -o wav_output/ -f wav
```

## Options
- `-f`, `--format`: Target audio format (`mp3`, `wav`, `flac`, `ogg`, `aac`, default: `mp3`).
- `-b`, `--bitrate`: Audio bitrate (`192k`, `256k`, `320k`, default: `192k`).
- `-ar`, `--samplerate`: Target sample rate in Hz (e.g. `44100`, `48000`).
- `-o`, `--output`: Destination directory.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `ffmpeg` binary on system PATH.

## Quality
Quality: pylint 10.00/10 · 84% coverage · 0 dependencies

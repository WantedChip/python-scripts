# Subtitle Fixer

A pure-Python CLI utility to shift timing, repair encoding, remove duplicates, and convert subtitle formats.

## Features

- **Shift Timings**: Shift all entry timestamps by positive or negative milliseconds.
- **Repair Encoding**: sniff file BOM bytes, validate UTF-8 or fall back to Windows-1252 to re-save files in clean UTF-8.
- **Deduplication**: Filter overlapping subtitle lines with customizable text similarity ratios.
- **Format Conversion**: Convert between SRT, WebVTT (VTT), and SSA/ASS formats.
- **Zero Dependencies**: Relies exclusively on Python's standard library.

## Usage

```bash
# Shift timings forward by 1.5 seconds (1500 ms) in-place
python subtitle_fixer.py -i movie.srt --in-place shift -s 1500

# Shift timings backward by 2 seconds and save as VTT format
python subtitle_fixer.py -i movie.srt -o movie_shifted.vtt shift -s -2000

# Convert SRT file to SSA/ASS format
python subtitle_fixer.py -i movie.srt -o movie.ass convert

# Filter out duplicate/overlapping lines
python subtitle_fixer.py -i movie.srt -o movie_deduped.srt dedup --threshold 0.8

# Run full sequence: repair encoding issues and filter duplicates
python subtitle_fixer.py -i movie.srt --in-place repair
```

## Requirements

- Python 3.x (standard library only)

## Notes

- Modifying files in-place with `--in-place` automatically creates a backup `.bak` file in the same directory.

Quality: pylint 10.00/10 · 93% coverage · 0 dependencies

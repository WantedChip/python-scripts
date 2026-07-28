# image-duplicate-finder

Finds visually similar or exact duplicate images in a folder using difference perceptual hashing (dHash) and Hamming distance bit comparisons.

## Usage

### Table Summary
```bash
python tools/image-duplicate-finder/image_duplicate_finder.py ~/Photos/ -t 4
```

### Export JSON Duplicate Report
```bash
python tools/image-duplicate-finder/image_duplicate_finder.py ~/Photos/ -f json
```

## Options
- `-t`, `--threshold`: Max Hamming distance similarity threshold (default: 4, 0=exact match).
- `-f`, `--format`: Output display format (`table`, `json`).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 88% coverage · 1 dependency

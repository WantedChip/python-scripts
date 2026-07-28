# image-color-palette-extractor

Extracts dominant color palettes from images and displays hex codes, RGB tuples, percentage distribution, and terminal ANSI color swatches.

## Usage

### Terminal Palette Display
```bash
python tools/image-color-palette-extractor/image_color_palette_extractor.py photo.jpg -n 5
```

### Export JSON / CSV
```bash
python tools/image-color-palette-extractor/image_color_palette_extractor.py photo.jpg -f json
python tools/image-color-palette-extractor/image_color_palette_extractor.py photo.jpg -f csv
```

## Options
- `-n`, `--num-colors`: Number of dominant colors to extract (default: 5).
- `-f`, `--format`: Output display format (`table`, `json`, `csv`).
- `--ignore-bg`: Skip pure white / near-white background colors.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 87% coverage · 1 dependency

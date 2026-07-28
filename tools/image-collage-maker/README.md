# image-collage-maker

Combines multiple images into a clean collage grid layout with customizable columns, spacing, cell slot dimensions, and background color.

## Usage

### Auto Grid Layout
```bash
python tools/image-collage-maker/image_collage_maker.py photos/ -o collage.jpg
```

### Specific Columns and Spacing
```bash
python tools/image-collage-maker/image_collage_maker.py photo1.jpg photo2.jpg photo3.jpg photo4.jpg -o grid.png -c 2 -s 15 --bg-color "#000000"
```

## Options
- `-o`, `--output`: Target collage output image path. Required.
- `-c`, `--cols`: Number of grid columns (auto-calculated if omitted).
- `--cell-width`: Slot width in pixels (default: 300).
- `--cell-height`: Slot height in pixels (default: 300).
- `-s`, `--spacing`: Cell spacing margin in pixels (default: 10).
- `--bg-color`: Canvas background color (default: `#FFFFFF`).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 84% coverage · 1 dependency

# batch-image-resizer

Resizes images in a directory or file with customizable dimensions, scaling percentages, maximum bounding dimensions, and aspect ratio options.

## Usage

### Max Dimension Resize
```bash
python tools/batch-image-resizer/batch_image_resizer.py photos/ -o output/ -m 1200
```

### Scale Factor (50% Size)
```bash
python tools/batch-image-resizer/batch_image_resizer.py photos/ -s 0.5
```

### Explicit Width and Height
```bash
python tools/batch-image-resizer/batch_image_resizer.py photo.jpg -w 800 -H 600 --no-aspect
```

## Options
- `-o`, `--output`: Output directory.
- `-w`, `--width`: Target width.
- `-H`, `--height`: Target height.
- `-s`, `--scale`: Scale factor (e.g. 0.5).
- `-m`, `--max-dim`: Max bounding dimension.
- `--no-aspect`: Stretch to fit (ignore aspect ratio).
- `-q`, `--quality`: Output JPEG quality (1-100).
- `--dry-run`: Preview sizes without saving files.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 88% coverage · 1 dependency

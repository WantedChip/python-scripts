# image-grayscale-converter

Converts color images to grayscale in bulk with adjustable contrast enhancement, brightness tuning, and optional sepia tone filtering.

## Usage

### Batch Grayscale Conversion
```bash
python converters/image-grayscale-converter/image_grayscale_converter.py photos/ -o gray_photos/
```

### Contrast and Brightness Adjustment
```bash
python converters/image-grayscale-converter/image_grayscale_converter.py photo.jpg -c 1.3 -b 1.1
```

### Vintage Sepia Tone
```bash
python converters/image-grayscale-converter/image_grayscale_converter.py photo.jpg --sepia
```

## Options
- `-o`, `--output`: Destination directory.
- `-c`, `--contrast`: Contrast multiplier factor (default: 1.0).
- `-b`, `--brightness`: Brightness multiplier factor (default: 1.0).
- `--sepia`: Apply vintage sepia tone filter.
- `--suffix`: Filename suffix (default: `_gray`).
- `-q`, `--quality`: Quality 1-100 (default: 90).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 85% coverage · 1 dependency

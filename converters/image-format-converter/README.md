# image-format-converter

Converts image files between formats (JPEG, PNG, WebP, BMP, TIFF) in bulk across a directory with RGBA transparency flattening.

## Usage

### Convert Directory to WebP
```bash
python converters/image-format-converter/image_format_converter.py photos/ -o output/ -f webp
```

### Convert PNG to JPEG with Custom Background
```bash
python converters/image-format-converter/image_format_converter.py logo.png -f jpg --bg-color "#FFFFFF"
```

## Options
- `-f`, `--format`: Target format (`jpg`, `png`, `webp`, `bmp`, `tiff`). Required.
- `-o`, `--output`: Output directory.
- `-q`, `--quality`: Quality 1-100 for JPEG/WebP.
- `--bg-color`: Hex background color for RGBA to JPEG flattening.
- `--remove-source`: Delete original files after successful conversion.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 90% coverage · 1 dependency

# image-border-adder

Adds decorative colored borders, matting frames, or polaroid-style borders to images for social media publishing.

## Usage

### Add Uniform Border
```bash
python tools/image-border-adder/image_border_adder.py photos/ -o framed/ -w 25 -c "#FFFFFF"
```

### Vintage Polaroid Frame
```bash
python tools/image-border-adder/image_border_adder.py photo.jpg --polaroid --bottom-margin 60
```

## Options
- `-w`, `--width`: Border width in pixels (default: 20).
- `-c`, `--color`: Border hex color (default: `#FFFFFF`).
- `--polaroid`: Vintage polaroid wide bottom border frame.
- `--bottom-margin`: Additional bottom margin for polaroid frame (default: 60).
- `-o`, `--output`: Destination directory.
- `--suffix`: Filename suffix (default: `_border`).
- `-q`, `--quality`: Quality 1-100 (default: 90).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 86% coverage · 1 dependency

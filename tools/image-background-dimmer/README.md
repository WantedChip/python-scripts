# image-background-dimmer

Dims image backgrounds using dark overlays or opacity adjustments to make overlaid text captions or graphics stand out with contrast.

## Usage

### Batch Background Dimming
```bash
python tools/image-background-dimmer/image_background_dimmer.py photos/ -o dimmed/ -d 0.5 -p 0.4
```

### Single Photo Processing
```bash
python tools/image-background-dimmer/image_background_dimmer.py photo.jpg --dim 0.3 --opacity 0.5
```

## Options
- `-d`, `--dim`: Brightness scale factor (0.0 to 1.0, default: 0.5).
- `-p`, `--opacity`: Dark overlay opacity (0.0 to 1.0, default: 0.4).
- `-o`, `--output`: Destination directory.
- `--suffix`: Filename suffix (default: `_dimmed`).
- `-q`, `--quality`: Quality 1-100 (default: 90).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 86% coverage · 1 dependency

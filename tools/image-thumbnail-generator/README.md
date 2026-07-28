# image-thumbnail-generator

Generates thumbnail versions of images with specified maximum bounding dimensions and optional square padding.

## Usage

### Batch Thumbnail Generation
```bash
python tools/image-thumbnail-generator/image_thumbnail_generator.py photos/ -o thumbnails/ -s 256
```

### Square Canvas Thumbnail
```bash
python tools/image-thumbnail-generator/image_thumbnail_generator.py photo.jpg -s 128 --square
```

## Options
- `-s`, `--size`: Maximum dimension in pixels (default: 256).
- `-o`, `--output`: Destination directory.
- `--square`: Pad into a square bounding canvas.
- `--suffix`: Filename suffix (default: `_thumb`).
- `-q`, `--quality`: Quality 1-100 (default: 85).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 86% coverage · 1 dependency

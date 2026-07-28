# image-rotation-corrector

Auto-detects EXIF orientation metadata tags in photos and transposes pixels to upright orientation in bulk.

## Usage

### Batch Rotation Correction
```bash
python tools/image-rotation-corrector/image_rotation_corrector.py photos/ -o upright_photos/
```

### In-Place File Update
```bash
python tools/image-rotation-corrector/image_rotation_corrector.py photo.jpg --in-place
```

## Options
- `-o`, `--output`: Destination directory.
- `--suffix`: Filename suffix (default: `_upright`).
- `--in-place`: Overwrite original files in-place.
- `-q`, `--quality`: Quality 1-100 (default: 90).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 84% coverage · 1 dependency

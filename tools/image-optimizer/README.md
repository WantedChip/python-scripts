# Image Optimization Pipeline

Recursively resize, compress, and convert images while preserving originals and metadata rules.

## Usage

```bash
# General help
python image_optimizer.py --help

# Process directory and output optimized WebP files to another folder, scaling down by 50%
python image_optimizer.py -i ./images -o ./optimized -f WEBP --scale 0.5

# Resize to exact dimensions (800x600) and compress JPEG with quality 80
python image_optimizer.py -i photo.jpg -o ./out --width 800 --height 600 -q 80

# Keep orientation EXIF tag but strip all other metadata
python image_optimizer.py -i photo.jpg -o ./out --metadata orientation

# Overwrite original files in-place without suffix
python image_optimizer.py -i ./photos --in-place --scale 0.8

# Run dry run preview showing files to process
python image_optimizer.py -i ./photos -o ./out --dry-run
```

## Requirements

- `Pillow==11.2.1`

## Notes

- Supports converting between `JPEG`, `PNG`, `WEBP`, `BMP`, and `TIFF`.
- Skips saving if input path equals output path unless `--in-place` is specified, protecting against accidental originals loss.

Quality: pylint 10.00/10 · 94% coverage · 1 dependencies

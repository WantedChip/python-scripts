# image-metadata-stripper

Removes EXIF metadata, IPTC headers, camera parameters, and GPS location geotags from images for privacy before sharing online.

## Usage

### Strip Directory
```bash
python tools/image-metadata-stripper/image_metadata_stripper.py photos/ -o clean_photos/
```

### Strip In-Place
```bash
python tools/image-metadata-stripper/image_metadata_stripper.py photo.jpg --in-place
```

## Options
- `-o`, `--output`: Destination directory.
- `--suffix`: Filename suffix (default: `_clean`).
- `--in-place`: Overwrite original files in-place.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 84% coverage · 1 dependency

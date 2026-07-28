# image-crop-center

Crops images to a specified aspect ratio (`1:1`, `16:9`, `4:3`, `4:5`, `3:2`, `9:16`) from the geometric center, ideal for profile avatars and social thumbnails.

## Usage

### Square Profile Crop (1:1)
```bash
python tools/image-crop-center/image_crop_center.py photos/ -o cropped/ -a 1:1
```

### Widescreen Banner Crop (16:9) with Resize
```bash
python tools/image-crop-center/image_crop_center.py photo.jpg -a 16:9 -w 1920 -H 1080
```

## Options
- `-a`, `--aspect-ratio`: Aspect ratio preset (`1:1`, `16:9`, `4:3`, `4:5`, `3:2`, `9:16`) or W:H ratio.
- `-w`, `--width`: Width to resize cropped output image.
- `-H`, `--height`: Height to resize cropped output image.
- `-f`, `--focal-position`: Vertical focus bias (`top`, `center`, `bottom`).
- `-o`, `--output`: Destination directory.
- `--suffix`: Filename suffix (default: `_crop`).
- `-q`, `--quality`: JPEG quality 1-100 (default: 90).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pillow==10.3.0`

## Quality
Quality: pylint 10.00/10 · 84% coverage · 1 dependency

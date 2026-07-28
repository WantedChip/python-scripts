# base64-image-encoder

Encodes image files into base64 Data URIs / strings for embedding into HTML/CSS files, or decodes base64 strings back to binary image files.

## Usage

### Encode Image to Base64
```bash
python converters/base64-image-encoder/base64_image_encoder.py encode photo.jpg -o photo_b64.txt
```

### Decode Base64 to Image
```bash
python converters/base64-image-encoder/base64_image_encoder.py decode photo_b64.txt -o restored.jpg
```

## Options
- `encode`: Encode mode. Options: `--raw` (strip Data URI prefix), `-o` output text file.
- `decode`: Decode mode. Options: `-o` target output image file path (required).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- Standard Library only (`base64`, `mimetypes`, `pathlib`, `argparse`).

## Quality
Quality: pylint 10.00/10 · 90% coverage · 0 dependencies

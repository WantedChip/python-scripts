# pdf-to-image-converter

Converts each page of a PDF to high-resolution PNG or JPEG image files.

## Usage

### Convert PDF Pages to PNG Images
```bash
python converters/pdf-to-image-converter/pdf_to_image_converter.py document.pdf -o output_dir/
```

### Convert Specific Page Ranges to JPEG
```bash
python converters/pdf-to-image-converter/pdf_to_image_converter.py document.pdf -r "1-3,5" -f jpeg -o output_dir/
```

## Options
- `-o`, `--output-dir`: Destination directory for output images.
- `-f`, `--format`: Target image format (`png`, `jpeg`).
- `-r`, `--ranges`: Page range filter (e.g. `1-3,5`).
- `-p`, `--password`: Password for encrypted PDFs.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`
- `Pillow==11.1.0`

## Quality
Quality: pylint 10.00/10 · 88% coverage · 2 dependencies

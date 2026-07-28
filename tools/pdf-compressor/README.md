# pdf-compressor

Reduces PDF file size by compressing content streams and deduplicating identical objects.

## Usage

### Compress Single PDF File
```bash
python tools/pdf-compressor/pdf_compressor.py document.pdf -o compressed.pdf
```

### Compress All PDFs in a Directory
```bash
python tools/pdf-compressor/pdf_compressor.py pdf_folder/ -o compressed_folder/
```

## Options
- `-o`, `--output`: Target compressed PDF path or directory.
- `-p`, `--password`: Password for encrypted PDFs.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 88% coverage · 1 dependency

# pdf-page-splitter

Splits a PDF into individual pages, page ranges, or page chunks.

## Usage

### Split Every Page into a Separate PDF File
```bash
python tools/pdf-page-splitter/pdf_page_splitter.py document.pdf -o split_pages/
```

### Extract Specific Page Ranges
```bash
python tools/pdf-page-splitter/pdf_page_splitter.py document.pdf -r "1-3,5,8-10"
```

### Split PDF into 5-Page Chunks
```bash
python tools/pdf-page-splitter/pdf_page_splitter.py document.pdf -c 5
```

## Options
- `-o`, `--output-dir`: Output directory for generated split PDFs.
- `-r`, `--ranges`: Page ranges to extract (e.g. `1-3,5,8-10`).
- `-c`, `--chunk-size`: Split into files of N pages each.
- `-p`, `--password`: Password for encrypted input PDF.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 88% coverage · 1 dependency

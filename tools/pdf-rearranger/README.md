# pdf-rearranger

Reorders, rotates, or deletes specific pages from a PDF file.

## Usage

### Reorder Pages
```bash
python tools/pdf-rearranger/pdf_rearranger.py document.pdf -r "3,1,2,4" -o reordered.pdf
```

### Delete Selected Pages
```bash
python tools/pdf-rearranger/pdf_rearranger.py document.pdf -d "2,5" -o trimmed.pdf
```

### Rotate Specific Pages Clockwise
```bash
python tools/pdf-rearranger/pdf_rearranger.py document.pdf --rotate 90 --rotate-pages "1,3" -o rotated.pdf
```

## Options
- `-r`, `--reorder`: Custom page order sequence (e.g. `3,1,2,4-5`).
- `--rotate`: Angle to rotate pages clockwise (`90`, `180`, `270`).
- `--rotate-pages`: Specific pages to rotate (e.g. `1,3`).
- `-d`, `--delete`: Pages to delete/exclude (e.g. `2,4`).
- `-o`, `--output`: Destination modified output PDF path.
- `-p`, `--password`: Password for encrypted PDF.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 88% coverage · 1 dependency

# pdf-merger

Combines multiple PDF files or all PDFs in a directory into a single document in a specified order.

## Usage

### Merge Individual PDF Files
```bash
python tools/pdf-merger/pdf_merger.py doc1.pdf doc2.pdf doc3.pdf -o combined.pdf
```

### Merge All PDFs in a Directory
```bash
python tools/pdf-merger/pdf_merger.py pdf_folder/ -o combined_folder.pdf
```

## Options
- `-o`, `--output`: Output merged PDF path (default: `merged.pdf`).
- `-b`, `--add-bookmarks`: Add outline bookmarks for each merged file.
- `-p`, `--password`: Password for encrypted input PDFs.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 86% coverage · 1 dependency

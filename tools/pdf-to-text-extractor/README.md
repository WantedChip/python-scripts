# pdf-to-text-extractor

Extracts plain text from PDF files (single file or batch directory) for indexing, NLP, or search processing.

## Usage

### Extract Text to Console
```bash
python tools/pdf-to-text-extractor/pdf_to_text_extractor.py document.pdf
```

### Save Extracted Text to File
```bash
python tools/pdf-to-text-extractor/pdf_to_text_extractor.py document.pdf -o extracted_text.txt
```

### Extract Text from Page Range to JSON Dataset
```bash
python tools/pdf-to-text-extractor/pdf_to_text_extractor.py pdf_folder/ -r "1-5,8" -f json -o output_dir/
```

## Options
- `-o`, `--output`: Destination text file path or directory (stdout if omitted).
- `-f`, `--format`: Output format (`txt`, `json`).
- `-r`, `--pages`: Page range filter (e.g. `1-5,7`).
- `-p`, `--password`: Password for encrypted PDFs.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 87% coverage · 1 dependency

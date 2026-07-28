# pdf-page-counter

Reports total page counts for all PDFs in a directory in a summary table, CSV, or JSON output.

## Usage

### Display Page Count Summary Table
```bash
python tools/pdf-page-counter/pdf_page_counter.py pdf_folder/
```

### Scan Subdirectories Recursively and Export CSV
```bash
python tools/pdf-page-counter/pdf_page_counter.py pdf_folder/ -r -o summary.csv
```

### Output JSON Format
```bash
python tools/pdf-page-counter/pdf_page_counter.py pdf_folder/ -f json
```

## Options
- `-r`, `--recursive`: Scan directory recursively.
- `-f`, `--format`: Console output format (`table`, `csv`, `json`).
- `-o`, `--output`: Output summary report file path.
- `-p`, `--password`: Default password for encrypted PDFs.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 88% coverage · 1 dependency

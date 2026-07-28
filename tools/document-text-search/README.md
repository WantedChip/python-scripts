# document-text-search

Searches for keywords or regex patterns across multiple PDF, TXT, CSV, JSON, and Markdown files in a folder.

## Usage

### Search Directory for Keyword
```bash
python tools/document-text-search/document_text_search.py folder/ "invoice"
```

### Search Subdirectories Recursively using Regex Pattern
```bash
python tools/document-text-search/document_text_search.py folder/ "error_\d+" --regex -r -o report.json
```

## Options
- `-r`, `--recursive`: Search subdirectories recursively.
- `--regex`: Treat query as regular expression.
- `-i`, `--ignore-case`: Case-insensitive search.
- `-f`, `--format`: Console output format (`table`, `json`, `csv`).
- `-o`, `--output`: Output report file path.
- `-p`, `--password`: Password for encrypted PDFs.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 90% coverage · 1 dependency

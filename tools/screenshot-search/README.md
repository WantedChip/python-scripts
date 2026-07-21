# screenshot-search

Scan and index a directory of screenshots recursively using local OCR and SQLite, allowing fast keyword queries (e.g. searching for text like "error about Docker" or "receipt from June") across all image content.

## Usage

Index a screenshot directory without searching:

```bash
python screenshot_search.py --scan-dir C:/Users/Name/Pictures/Screenshots --index-only
```

Search the screenshot index database for keywords:

```bash
python screenshot_search.py "Docker error"
```

Customize search index database destination paths:

```bash
python screenshot_search.py "June receipt" --db-path my_custom_index.db
```

## Requirements

- Python 3.11+
- Pillow & pytesseract (listed in [requirements.txt](requirements.txt))
- Local Tesseract OCR engine binary installed on your OS

## Notes

- Attempts to locate the Tesseract binary automatically in standard system PATH and installation folders (`C:\Program Files\Tesseract-OCR\tesseract.exe`).
- Performs incremental indexing (only running OCR on files created or modified since the last index run).

## Quality

Quality: pylint 10.00/10 · 100% coverage · 2 dependencies

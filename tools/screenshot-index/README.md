# Screenshot Index & Search Tool

Local OCR screenshot indexer powered by SQLite. Easily find past screenshots by remembered keywords, application names, date ranges, or topic tags.

## Features
- **SQLite Database**: Lightweight local storage of OCR text, file paths, app metadata, and creation dates.
- **Flexible Search Filters**: Query by keyword substring, application name, start/end dates (`YYYY-MM-DD`), and topics.
- **CLI Commands**: Convenient command-line interface for indexing and searching.
- **Mock Fallback**: Works in environments without Tesseract OCR binary.

## Requirements
```bash
pip install -r requirements.txt
```

## Usage

### Indexing a screenshot:
```bash
python main.py index --file ~/Pictures/screenshot1.png --app Chrome --topic "Python API" --date 2026-07-24
```

### Searching screenshots:
```bash
python main.py search --query "database connection" --app Chrome --start-date 2026-07-01
```

## Running Tests
```bash
python -m unittest discover tests
```

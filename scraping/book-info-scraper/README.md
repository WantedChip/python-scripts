# Book Info Scraper

Extracts book metadata by ISBN (ISBN-10 and ISBN-13) using the Open Library API and formats the output into terminal cards, JSON, or Markdown documents.

## Features

- **ISBN Validation**: Checks algorithmically valid ISBN-10 and ISBN-13 strings (with or without hyphens).
- **Open Library API Integration**: Queries `openlibrary.org` REST API for title, authors, publication date, publishers, page count, and subjects.
- **Multiple Output Formats**: ASCII terminal card, JSON, and Markdown format.
- **Zero External Dependencies**: Built entirely using Python standard library modules.

## Usage

```bash
# Display terminal summary card
python main.py 9780135957059

# Export to JSON
python main.py 9780135957059 --format json -o book.json

# Export to Markdown
python main.py 032157351X --format markdown -o book.md
```

## Running Tests

```bash
python -m unittest discover -s tests
```

# Random Quote Fetcher

Fetches random quotes from public quote APIs (Quotable, DummyJSON) with optional category/author filters, and exports formatted results in Text, JSON, or Markdown formats.

## Features

- Fetch one or multiple random quotes.
- Filter by tag/category (e.g. `technology`, `inspirational`, `wisdom`) and author.
- Export in **Text**, **JSON**, or **Markdown** formats.
- Supports overwriting or appending to output files.

## Usage

```bash
# Print a single random quote
python main.py

# Fetch 3 quotes in inspirational category
python main.py -n 3 -t inspirational

# Export as Markdown blockquotes to a file
python main.py -n 5 -f markdown -o quotes.md

# Append JSON formatted quotes to quotes.json
python main.py -n 2 -f json -o quotes.json --append
```

## Requirements

Python 3.8+ (Standard Library only).

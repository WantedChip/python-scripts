# Quote of the Day Scraper CLI

A Python CLI tool to fetch daily inspirational quotes from public quote APIs and append them as formatted Markdown blocks into a personal collection file with automatic deduplication.

## Features
- **API Fetching**: Supports ZenQuotes, DummyJSON, and Quotable APIs.
- **Automatic Deduplication**: Prevents adding duplicate quotes to your collection file.
- **Markdown Formatting**: Renders quotes into clean blockquotes with metadata (date, author, category).
- **Offline Resiliency**: Built-in fallback quote generator if API endpoints are unreachable.

## Usage

```bash
# Fetch daily quote and append to quotes.md
python main.py

# Specify custom output file and category
python main.py -o my_journal.md -c Motivation

# Choose specific API source
python main.py -s dummyjson

# Force append even if duplicate
python main.py --force
```

## Running Tests

```bash
python -m unittest discover -s tests
```

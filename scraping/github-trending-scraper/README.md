# GitHub Trending Scraper

Fetches trending repositories on GitHub filtered by language and date range using the GitHub REST Search API and HTML parsing fallback.

## Features

- **Language Filtering**: Filter repositories by language (e.g. Python, Rust, TypeScript).
- **Timeframe Filtering**: Daily, weekly, or monthly date calculation.
- **Rich Metadata**: Name, author, URL, language, star count, fork count, and description.
- **Export Formats**: Markdown table, JSON, and ASCII terminal table.

## Usage

```bash
# Fetch top weekly trending Python repositories in Markdown
python main.py --language python --since weekly --format markdown

# Fetch top 10 Rust projects as JSON
python main.py --language rust --limit 10 --format json -o trending_rust.json

# Display ASCII table for daily trends
python main.py --since daily --format terminal
```

## Running Tests

```bash
python -m unittest discover -s tests
```

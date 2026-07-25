# News Headline Scraper

A Python CLI tool to scrape and summarize top news headlines from RSS/Atom feeds or websites, with keyword filtering and Markdown/JSON export options.

## Features
- **Feed & HTML Parsing**: Supports RSS 2.0, Atom feeds, and website scraping.
- **Keyword Filtering**: Filter news stories by specific topics or search terms.
- **Multiple Formats**: Export results into clean Markdown documents or JSON.
- **CLI Options**: Custom limit, output file paths, and format selection.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Scrape default RSS feed (Hacker News RSS) to Markdown
python main.py

# Scrape specific RSS feed with keyword filter and save to Markdown
python main.py --url "https://feeds.bbci.co.uk/news/rss.xml" --keyword "technology" -o tech_news.md

# Save top 5 headlines to JSON
python main.py --limit 5 -o headlines.json
```

## Running Tests

```bash
python -m unittest discover -s tests
```

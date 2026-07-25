# Event Listing Scraper

Scrapes event listings from community websites or iCal/JSON feeds and filters by date range, category, and venue location.

## Features
- **Multi-Format Parsing**: Supports JSON-LD (`application/ld+json`), iCalendar (`.ics`), and HTML structures.
- **Flexible Filtering**: Filter by start/end dates, category names, or location substrings.
- **Multiple Exporters**: Output results to Markdown (`.md`), iCalendar (`.ics`), or JSON (`.json`).

## Usage

```bash
# Parse from a file and export to Markdown
python main.py --file events.html --export-format md --output events.md

# Filter events by category and location
python main.py --file feed.ics --category Education --location Online

# Parse from URL and filter by date range
python main.py --url https://example.com/events --start-date 2026-09-01 --end-date 2026-12-31 --export-format json
```

## Running Tests

```bash
python -m unittest discover tests
```

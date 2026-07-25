# Country Info Fetcher

A Python CLI tool to retrieve country data (capital, population, region, flag URL, currency, languages) from REST Countries API.

## Features
- Lookup country facts by full name or keyword.
- Formats population, area, languages, and map URLs into a terminal card.
- Export parsed country datasets to JSON or CSV files.

## Usage

```bash
# Display facts card for Japan
python main.py japan

# Lookup and export to JSON
python main.py "united kingdom" --json uk.json

# Save multiple matching results to CSV
python main.py korea --csv korea_countries.csv
```

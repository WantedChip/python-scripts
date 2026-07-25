# University Search Fetcher

A Python CLI tool to search universities worldwide by country name or title via the Hipolabs Universities API.

## Features
- Search by country name, university name, or both.
- Extracts domains, state/province, and official website URLs.
- Formatted terminal table output.
- Export full search results to JSON or CSV files.

## Usage

```bash
# Search universities in Canada
python main.py --country Canada

# Search universities containing 'Oxford'
python main.py --name Oxford

# Search tech universities in Germany and export to CSV
python main.py --country Germany --name Tech --csv germany_tech_unis.csv

# Export all matching results to JSON
python main.py --country Japan --json japan_unis.json
```

# Public Holiday Fetcher

Retrieves public holidays for any country code and year using the Nager.Date public API.

## Features

- Search by 2-letter country code (e.g. `US`, `GB`, `DE`, `IN`, `JP`).
- Support for current, historical, or future years.
- Filter to display only upcoming holidays.
- Terminal table and JSON formatting options.
- Export results to file.

## Usage

```bash
# Fetch US holidays for the current year
python main.py

# Fetch UK holidays for 2025 in JSON format
python main.py -c GB -y 2025 -f json

# Show only upcoming holidays for Germany
python main.py -c DE --upcoming

# Save holiday table to a file
python main.py -c IN -o holidays_india.txt
```

## Requirements

Python 3.8+ (Standard Library only).

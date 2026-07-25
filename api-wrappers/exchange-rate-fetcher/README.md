# Exchange Rate Fetcher

Fetches current or historical exchange rates between base and target currencies from free exchange rate APIs (open.er-api.com and Frankfurter API).

## Features

- Real-time and historical exchange rate lookups (`YYYY-MM-DD`).
- Custom base currency specification (e.g. `USD`, `EUR`, `GBP`, `JPY`).
- Multiple target currency filters and custom conversion amount.
- Terminal table format and JSON export support.

## Usage

```bash
# Get exchange rates for 1 USD to major currencies
python main.py

# Convert 250 EUR to USD, GBP, JPY
python main.py -b EUR -t USD,GBP,JPY -a 250

# Fetch historical exchange rates for 2024-01-15
python main.py -b USD -d 2024-01-15

# Save conversion rates as JSON file
python main.py -b GBP -f json -o rates.json
```

## Requirements

Python 3.8+ (Standard Library only).

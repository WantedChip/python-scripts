# Stock Price Scraper & Logger

Scrapes stock quotes (price, high/low, volume, percentage change) and appends historical quote snapshots to CSV log files.

## Features
- **Quote Metrics**: Fetches current price, daily high/low, volume, previous close, absolute change, and percentage change.
- **Provider Support**: Supports Stooq, Yahoo Finance API, and an offline mock provider strategy.
- **Historical CSV Logging**: Automatically creates or appends to structured CSV files for continuous stock tracking.

## Usage

```bash
# Fetch quotes for multiple tickers and append to CSV log
python main.py --tickers AAPL,MSFT,GOOGL --csv-file quotes.csv --summary

# Use mock provider for testing offline
python main.py --tickers TSLA,AMZN --provider mock --summary
```

## Running Tests

```bash
python -m unittest discover tests
```

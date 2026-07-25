# Bitcoin Price Fetcher

A Python CLI tool to retrieve current Bitcoin and cryptocurrency prices, 24h change %, market cap, and volume from CoinGecko API (with CoinDesk fallback).

## Features
- Query current price, market cap, and 24h stats for Bitcoin or any altcoin.
- Set high / low threshold price alert notifications.
- Log timestamped price ticker entries to CSV.
- CoinDesk API fallback for Bitcoin queries if CoinGecko rate limit triggers.

## Usage

```bash
# Fetch Bitcoin ticker in USD
python main.py

# Fetch Ethereum price in EUR
python main.py --coin ethereum --currency eur

# Set price alert thresholds
python main.py --alert-above 70000 --alert-below 50000

# Log current price to CSV file
python main.py --log-csv btc_tracker.csv
```

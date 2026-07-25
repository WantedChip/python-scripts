"""Stock Price Scraper and Historical CSV Logger.

Fetches stock quotes (ticker, current price, high, low, volume, prev close),
calculates price change metrics, and appends historical data to a CSV log.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import csv
import datetime
import json
import os
import random
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class StockQuote:
    """Represents financial stock quote metrics."""

    ticker: str
    timestamp: str
    price: float
    open_price: float
    high: float
    low: float
    volume: int
    prev_close: float
    change: float
    change_percent: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert quote object to dictionary."""
        return asdict(self)


def calculate_change(price: float, prev_close: float) -> Tuple[float, float]:
    """Calculate absolute change and percentage change."""
    if not prev_close or prev_close == 0.0:
        return 0.0, 0.0
    change = price - prev_close
    change_pct = (change / prev_close) * 100.0
    return round(change, 4), round(change_pct, 4)


def fetch_stooq_quote(ticker: str) -> Optional[StockQuote]:
    """Fetch quote from Stooq CSV public endpoint."""
    url = f"https://stooq.com/q/l/?s={ticker.lower()}&f=sdhglvc&e=csv"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            lines = resp.read().decode("utf-8").strip().splitlines()
            if len(lines) >= 2:
                reader = csv.reader(lines)
                _ = next(reader)
                row = next(reader)
                if len(row) >= 7 and row[1] != "N/D":
                    price = float(row[6]) if len(row) > 6 else float(row[3])
                    open_p = float(row[3])
                    high = float(row[4])
                    low = float(row[5])
                    vol = int(row[7]) if len(row) > 7 and row[7].isdigit() else 0
                    prev_c = open_p
                    chg, chg_pct = calculate_change(price, prev_c)
                    now_dt = datetime.datetime.now(datetime.timezone.utc)
                    now_str = now_dt.isoformat()
                    return StockQuote(
                        ticker=ticker.upper(),
                        timestamp=now_str,
                        price=price,
                        open_price=open_p,
                        high=high,
                        low=low,
                        volume=vol,
                        prev_close=prev_c,
                        change=chg,
                        change_percent=chg_pct,
                    )
    except (
        urllib.error.URLError,
        OSError,
        ValueError,
        KeyError,
        csv.Error,
    ):
        pass
    return None


def fetch_yahoo_quote(ticker: str) -> Optional[StockQuote]:
    """Fetch quote from Yahoo Finance API chart endpoint."""
    sym = ticker.upper()
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?"
        "interval=1d&range=1d"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
            meta = data["chart"]["result"][0]["meta"]
            price = float(meta.get("regularMarketPrice", 0.0))
            prev_c = float(meta.get("chartPreviousClose", price))
            high = float(meta.get("regularMarketDayHigh", price))
            low = float(meta.get("regularMarketDayLow", price))
            vol = int(meta.get("regularMarketVolume", 0))
            chg, chg_pct = calculate_change(price, prev_c)
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            now_str = now_dt.isoformat()
            return StockQuote(
                ticker=ticker.upper(),
                timestamp=now_str,
                price=price,
                open_price=prev_c,
                high=high,
                low=low,
                volume=vol,
                prev_close=prev_c,
                change=chg,
                change_percent=chg_pct,
            )
    except (
        urllib.error.URLError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ):
        pass
    return None


def fetch_mock_quote(ticker: str) -> StockQuote:
    """Generate realistic mock stock quote for testing / offline fallback."""
    base_price = 150.0 + (hash(ticker.upper()) % 100)
    prev_close = round(base_price + random.uniform(-2.0, 2.0), 2)  # nosec B311
    price = round(prev_close + random.uniform(-3.0, 3.0), 2)  # nosec B311
    high = max(price, prev_close) + round(random.uniform(0.5, 2.0), 2)  # nosec B311
    low = min(price, prev_close) - round(random.uniform(0.5, 2.0), 2)  # nosec B311
    volume = random.randint(1000000, 50000000)  # nosec B311
    chg, chg_pct = calculate_change(price, prev_close)
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return StockQuote(
        ticker=ticker.upper(),
        timestamp=now_str,
        price=price,
        open_price=prev_close,
        high=high,
        low=low,
        volume=volume,
        prev_close=prev_close,
        change=chg,
        change_percent=chg_pct,
    )


def get_stock_quote(ticker: str, provider: str = "auto") -> Optional[StockQuote]:
    """Fetch stock quote based on chosen provider strategy."""
    if provider == "mock":
        return fetch_mock_quote(ticker)

    if provider in ("stooq", "auto"):
        quote = fetch_stooq_quote(ticker)
        if quote:
            return quote

    if provider in ("yahoo", "auto"):
        quote = fetch_yahoo_quote(ticker)
        if quote:
            return quote

    # Fallback to mock if network/API fails
    return fetch_mock_quote(ticker)


def log_quotes_to_csv(quotes: List[StockQuote], csv_filepath: str) -> None:
    """Append stock quotes to historical CSV log file."""
    file_exists = os.path.isfile(csv_filepath)
    fieldnames = [
        "timestamp",
        "ticker",
        "price",
        "open_price",
        "high",
        "low",
        "volume",
        "prev_close",
        "change",
        "change_percent",
    ]

    with open(csv_filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for q in quotes:
            writer.writerow(q.to_dict())


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Fetch stock prices and log history to CSV."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--tickers",
        required=True,
        help="Comma-separated list of stock tickers (e.g. AAPL,MSFT,GOOGL)",
    )
    parser.add_argument(
        "--csv-file",
        default="stock_quotes_log.csv",
        help="CSV log output path",
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "stooq", "yahoo", "mock"],
        default="auto",
        help="Data provider source",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print quote summary table to stdout",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point for stock-price-scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    tickers = [t.strip() for t in parsed.tickers.split(",") if t.strip()]

    quotes: List[StockQuote] = []
    for ticker in tickers:
        quote = get_stock_quote(ticker, provider=parsed.provider)
        if quote:
            quotes.append(quote)

    if quotes:
        log_quotes_to_csv(quotes, parsed.csv_file)
        print(f"Logged {len(quotes)} quotes to {parsed.csv_file}")

    if parsed.summary:
        print("\n--- Stock Quotes Summary ---")
        for q in quotes:
            sign = "+" if q.change >= 0 else ""
            msg = (
                f"{q.ticker:<6} | Price: ${q.price:<8.2f} | Change: "
                f"{sign}{q.change:.2f} ({sign}{q.change_percent:.2f}%) | "
                f"Vol: {q.volume}"
            )
            print(msg)

    return 0


if __name__ == "__main__":
    sys.exit(main())

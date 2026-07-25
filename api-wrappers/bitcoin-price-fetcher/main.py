#!/usr/bin/env python3
"""Bitcoin & Crypto Price Fetcher script.

Retrieves current Bitcoin/crypto price, market cap, and 24h change from CoinGecko
API with fallback support.
Formats ticker cards, evaluates threshold price alerts, and logs prices to CSV.
"""

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price"
COINDESK_API_URL = "https://api.coindesk.com/v1/bpi/currentprice.json"


def fetch_json(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Fetch JSON response from an API URL.

    Args:
        url: Endpoint URL string.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON dictionary or None on failure.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "BitcoinPriceFetcher/1.0 (Python)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                return cast(Dict[str, Any], json.loads(response.read().decode("utf-8")))
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error fetching from {url}: {err}", file=sys.stderr)
    return None


def fetch_coingecko_price(
    coin_id: str = "bitcoin", vs_currency: str = "usd"
) -> Optional[Dict[str, Any]]:
    """Fetch crypto price from CoinGecko API.

    Args:
        coin_id: Coin identifier (e.g. bitcoin, ethereum).
        vs_currency: Target fiat currency (e.g. usd, eur).

    Returns:
        Dictionary containing price stats or None.
    """
    params = urllib.parse.urlencode(
        {
            "ids": coin_id.strip().lower(),
            "vs_currencies": vs_currency.strip().lower(),
            "include_market_cap": "true",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
        }
    )
    url = f"{COINGECKO_API_URL}?{params}"
    data = fetch_json(url)
    if data and coin_id in data:
        coin_data = data[coin_id]
        curr = vs_currency.lower()
        return {
            "source": "CoinGecko",
            "coin": coin_id,
            "currency": vs_currency.upper(),
            "price": coin_data.get(curr, 0.0),
            "market_cap": coin_data.get(f"{curr}_market_cap", 0.0),
            "change_24h": coin_data.get(f"{curr}_24h_change", 0.0),
            "volume_24h": coin_data.get(f"{curr}_24h_vol", 0.0),
        }
    return None


def fetch_coindesk_bitcoin_price() -> Optional[Dict[str, Any]]:
    """Fallback method: Fetch Bitcoin price from CoinDesk API.

    Returns:
        Dictionary containing price stats or None.
    """
    data = fetch_json(COINDESK_API_URL)
    if data and "bpi" in data:
        usd_info = data["bpi"].get("USD", {})
        price = usd_info.get("rate_float", 0.0)
        return {
            "source": "CoinDesk",
            "coin": "bitcoin",
            "currency": "USD",
            "price": price,
            "market_cap": 0.0,
            "change_24h": 0.0,
            "volume_24h": 0.0,
        }
    return None


def fetch_crypto_price(
    coin_id: str = "bitcoin", vs_currency: str = "usd"
) -> Optional[Dict[str, Any]]:
    """Fetch cryptocurrency price with automatic API fallback.

    Args:
        coin_id: Coin identifier (default: bitcoin).
        vs_currency: Fiat currency (default: usd).

    Returns:
        Structured price stats dictionary or None.
    """
    result = fetch_coingecko_price(coin_id, vs_currency)
    if not result and coin_id.lower() == "bitcoin" and vs_currency.lower() == "usd":
        print(
            "CoinGecko API unavailable. Attempting CoinDesk fallback...",
            file=sys.stderr,
        )
        result = fetch_coindesk_bitcoin_price()
    return result


def check_price_alerts(
    price: float, alert_above: Optional[float], alert_below: Optional[float]
) -> List[str]:
    """Check if price triggers any user-defined threshold alerts.

    Args:
        price: Current price float.
        alert_above: Price ceiling threshold float.
        alert_below: Price floor threshold float.

    Returns:
        List of alert message strings.
    """
    alerts: List[str] = []
    if alert_above is not None and price >= alert_above:
        alerts.append(
            f"HIGH ALERT: Current price ${price:,.2f} is ABOVE "
            f"threshold of ${alert_above:,.2f}!"
        )
    if alert_below is not None and price <= alert_below:
        alerts.append(
            f"LOW ALERT: Current price ${price:,.2f} is BELOW "
            f"threshold of ${alert_below:,.2f}!"
        )
    return alerts


def format_ticker_card(data: Dict[str, Any]) -> str:
    """Format crypto stats into a terminal ticker card display.

    Args:
        data: Price stats dictionary.

    Returns:
        Formatted ASCII string representation of ticker statistics.
    """
    coin = data.get("coin", "CRYPTO").upper()
    currency = data.get("currency", "USD")
    price = data.get("price", 0.0)
    change = data.get("change_24h", 0.0)
    mcap = data.get("market_cap", 0.0)
    vol = data.get("volume_24h", 0.0)
    source = data.get("source", "API")

    change_sign = "+" if change > 0 else ""
    change_str = f"{change_sign}{change:.2f}%"

    lines = [
        "==================================================",
        f"  CRYPTO TICKER: {coin} / {currency}",
        "==================================================",
        f"  Current Price : ${price:,.2f} {currency}",
        f"  24h Change    : {change_str}",
        f"  Market Cap    : ${mcap:,.0f}" if mcap else "  Market Cap    : N/A",
        f"  24h Volume    : ${vol:,.0f}" if vol else "  24h Volume    : N/A",
        f"  Data Source   : {source}",
        "==================================================",
    ]
    return "\n".join(lines)


def log_price_to_csv(filepath: str, data: Dict[str, Any]) -> bool:
    """Append timestamped crypto price entry to CSV log file.

    Args:
        filepath: CSV output file path.
        data: Price data dictionary.

    Returns:
        True if logged successfully, False otherwise.
    """
    file_exists = os.path.isfile(filepath)
    now_iso = datetime.now(timezone.utc).isoformat()

    row = {
        "timestamp": now_iso,
        "coin": data.get("coin"),
        "currency": data.get("currency"),
        "price": data.get("price"),
        "change_24h": data.get("change_24h"),
        "market_cap": data.get("market_cap"),
        "source": data.get("source"),
    }

    try:
        with open(filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
        return True
    except OSError as err:
        print(f"Error logging to CSV file {filepath}: {err}", file=sys.stderr)
        return False


def main() -> None:
    """Main CLI entrypoint for Bitcoin Price Fetcher."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Bitcoin and crypto prices, check threshold alerts, and log to CSV."
        )
    )
    parser.add_argument(
        "--coin", "-c", default="bitcoin", help="Cryptocurrency ID (default: bitcoin)"
    )
    parser.add_argument(
        "--currency", default="usd", help="Target fiat currency (default: usd)"
    )
    parser.add_argument(
        "--alert-above",
        type=float,
        help="Trigger alert if price rises above this value",
    )
    parser.add_argument(
        "--alert-below",
        type=float,
        help="Trigger alert if price drops below this value",
    )
    parser.add_argument("--log-csv", help="CSV file path to log current price entry")

    args = parser.parse_args()

    print(
        f"Fetching price ticker for '{args.coin.upper()}' ({args.currency.upper()})..."
    )
    data = fetch_crypto_price(args.coin, args.currency)

    if not data:
        print(f"Could not fetch price data for coin '{args.coin}'.", file=sys.stderr)
        sys.exit(1)

    print(format_ticker_card(data))

    alerts = check_price_alerts(data["price"], args.alert_above, args.alert_below)
    for alert in alerts:
        print(f"\n[ALERT] {alert}")

    if args.log_csv:
        if log_price_to_csv(args.log_csv, data):
            print(f"Logged price entry to {args.log_csv}")


if __name__ == "__main__":
    main()

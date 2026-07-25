"""Exchange Rate Fetcher.

Fetches current or historical exchange rates between base and target currencies
from free APIs (open.er-api.com / Frankfurter API).
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


def fetch_exchange_rates(
    base: str = "USD", date: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch exchange rates for base currency.

    Args:
        base: Base currency symbol (e.g. USD, EUR, GBP).
        date: Optional historical date string in YYYY-MM-DD format.

    Returns:
        Dict containing base currency, date/last updated, and rates dictionary.

    Raises:
        ValueError: If currency code or date format is invalid.
        RuntimeError: On HTTP error or network failure.
    """
    base_code = base.strip().upper()

    if date:
        date_str = date.strip()
        url = f"https://api.frankfurter.app/{date_str}?from={base_code}"
    else:
        url = f"https://open.er-api.com/v6/latest/{base_code}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ExchangeRateFetcher/1.0 (Python)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if "rates" in data:
                    rates = data["rates"]
                    date_info = data.get("date") or data.get(
                        "time_last_update_utc", "Current"
                    )
                    return {"base": base_code, "date": date_info, "rates": rates}
                if data.get("result") == "error":
                    raise ValueError(f"API Error: {data.get('error-type')}")
            raise RuntimeError(f"HTTP Error {response.status}")
    except urllib.error.HTTPError as err:
        if err.code in (400, 404):
            raise ValueError(
                f"Invalid base currency '{base_code}' or date '{date}'."
            ) from err
        raise RuntimeError(f"HTTP Error {err.code}: {err.reason}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"Network error: {err.reason}") from err


def convert_currency(
    amount: float,
    base: str,
    target_currencies: Optional[List[str]],
    rates_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Convert amount to target currencies using fetched rates.

    Args:
        amount: Base amount to convert.
        base: Base currency code.
        target_currencies: Optional list of target currency codes.
        rates_data: Data returned by fetch_exchange_rates.

    Returns:
        List of conversion result dicts.
    """
    all_rates = rates_data.get("rates", {})
    results: List[Dict[str, Any]] = []

    if target_currencies:
        targets = [t.strip().upper() for t in target_currencies]
    else:
        # Default major currencies if none specified
        default_majors = ["EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "INR"]
        targets = [t for t in default_majors if t in all_rates and t != base]

    for target in targets:
        rate = all_rates.get(target)
        if rate is not None:
            converted = amount * rate
            results.append(
                {
                    "base": base,
                    "target": target,
                    "amount": amount,
                    "rate": round(rate, 6),
                    "converted_amount": round(converted, 2),
                }
            )

    return results


def format_rate_table(
    conversion_results: List[Dict[str, Any]], base: str, date: str
) -> str:
    """Format conversion results into a clean terminal table.

    Args:
        conversion_results: List of conversion dictionaries.
        base: Base currency symbol.
        date: Rate date string.

    Returns:
        Formatted tabular string.
    """
    if not conversion_results:
        return f"No exchange rates found for base '{base}'."

    header = f"Exchange Rates for {base} (Date/Updated: {date})"
    header_cols = (
        f"{'Base Amount':<15} | {'Target':<8} | "
        f"{'Exchange Rate':<15} | {'Converted Total':<15}"
    )
    lines = [
        header,
        "=" * len(header),
        header_cols,
        "-" * 62,
    ]

    for res in conversion_results:
        base_str = f"{res['amount']:,.2f} {res['base']}"
        conv_str = f"{res['converted_amount']:,.2f} {res['target']}"
        tgt = res["target"]
        rate = res["rate"]
        lines.append(f"{base_str:<15} | {tgt:<8} | {rate:<15.6f} | {conv_str:<15}")

    return "\n".join(lines)


def main() -> None:
    """CLI entry point for Exchange Rate Fetcher."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch current or historical exchange rates and convert currency amounts."
        )
    )
    parser.add_argument(
        "-b",
        "--base",
        default="USD",
        help="Base currency code (default: USD).",
    )
    parser.add_argument(
        "-t",
        "--target",
        help="Comma-separated target currency codes (e.g. EUR,GBP,JPY,CAD).",
    )
    parser.add_argument(
        "-a",
        "--amount",
        type=float,
        default=1.0,
        help="Amount to convert (default: 1.0).",
    )
    parser.add_argument(
        "-d",
        "--date",
        help="Historical date (YYYY-MM-DD). Default: latest.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format: table or json (default: table).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Save results to specified output JSON or TXT file.",
    )

    args = parser.parse_args()

    try:
        rates_data = fetch_exchange_rates(base=args.base, date=args.date)

        target_list = args.target.split(",") if args.target else None
        conversions = convert_currency(
            amount=args.amount,
            base=args.base.upper(),
            target_currencies=target_list,
            rates_data=rates_data,
        )

        if args.format == "json":
            export_payload = {
                "base": args.base.upper(),
                "date": rates_data.get("date"),
                "conversions": conversions,
            }
            output_str = json.dumps(export_payload, indent=2)
        else:
            output_str = format_rate_table(
                conversions, base=args.base.upper(), date=str(rates_data.get("date"))
            )

        print(output_str)

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                if args.format == "json" or args.output.suffix.lower() == ".json":
                    export_payload = {
                        "base": args.base.upper(),
                        "date": rates_data.get("date"),
                        "conversions": conversions,
                    }
                    json.dump(export_payload, f, indent=2)
                else:
                    f.write(output_str)
            print(f"\nExchange rate data saved to {args.output}")

    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

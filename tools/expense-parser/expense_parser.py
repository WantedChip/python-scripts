"""CLI Expense Parser.

A utility to parse bank-export CSV files, normalize dates and amounts,
auto-categorize transactions using rule matching, and output monthly summaries.
"""

import argparse
import collections
import csv
import datetime
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("expense_parser")

DEFAULT_RULES = {
    "Food & Dining": [
        "starbucks",
        "mcdonald",
        "grocery",
        "supermarket",
        "restaurant",
        "eats",
        "diner",
        "cafe",
    ],
    "Bills & Utilities": [
        "electric",
        "power",
        "water",
        "gas",
        "internet",
        "comcast",
        "netflix",
        "spotify",
        "insurance",
    ],
    "Rent & Housing": ["rent", "mortgage", "housing", "landlord"],
    "Transportation": [
        "uber",
        "lyft",
        "taxi",
        "transit",
        "subway",
        "metro",
        "shell",
        "chevron",
        "gasoline",
    ],
    "Shopping": ["amazon", "target", "walmart", "shopping", "store", "mall", "ebay"],
    "Income": ["payroll", "salary", "deposit", "dividend", "interest", "stripe"],
}


def setup_logging(verbose: bool) -> None:
    """Configure logging level and stream handler."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def parse_amount(val_str: str) -> float:
    """Parse numeric amount from currency/bank formatting strings.

    Args:
        val_str: messy numeric string e.g. '$1,234.56', '(100.00)', '120,50'

    Returns:
        float representing transaction amount.
    """
    cleaned = val_str.strip()
    if not cleaned:
        return 0.0

    # 1. Handle brackets for negative values: (120.00) -> -120.00
    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()

    # Strip currency symbols and whitespaces
    cleaned = re.sub(r"[^\d,\.\-]", "", cleaned)

    # 2. Check for minus sign
    if cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:].strip()

    # 3. Comma/dot decimal heuristic
    if "," in cleaned and "." not in cleaned:
        # Check if there is only one comma
        if cleaned.count(",") == 1:
            cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        comma_idx = cleaned.find(",")
        dot_idx = cleaned.find(".")
        if dot_idx < comma_idx:
            # European layout: e.g. 1.234,56
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # English layout: e.g. 1,234.56
            cleaned = cleaned.replace(",", "")

    try:
        val = float(cleaned)
        return -val if is_negative else val
    except ValueError:
        logger.warning("Could not parse amount string: '%s'", val_str)
        return 0.0


def parse_date(date_str: str) -> Optional[datetime.date]:
    """Parse date from common formats.

    Args:
        date_str: input date string (e.g. '10/07/2026', '2026-07-10', '10-Jul-26')

    Returns:
        date object or None.
    """
    cleaned = date_str.strip()
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%y-%m-%d",
        "%d/%m/%y",
        "%m/%d/%y",
        "%d-%b-%y",
        "%d-%b-%Y",
        "%d-%B-%y",
        "%d-%B-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def categorize_transaction(description: str, rules: Dict[str, List[str]]) -> str:
    """Categorize transaction description using keyword rules.

    Args:
        description: transaction payee/description string.
        rules: dictionary mapping category name to list of keywords.

    Returns:
        The matched category string or 'Other'.
    """
    desc_lower = description.lower()
    for category, keywords in rules.items():
        for keyword in keywords:
            if keyword.lower() in desc_lower:
                return category
    return "Other"


def detect_columns(header: List[str]) -> Tuple[int, int, int]:
    """Detect column indices for date, amount, description using heuristics.

    Args:
        header: lowercase list of CSV column header fields.

    Returns:
        Tuple of (date_idx, amount_idx, desc_idx).
    """
    date_idx = -1
    amount_idx = -1
    desc_idx = -1

    for idx, field in enumerate(header):
        field_clean = field.strip().lower()
        if date_idx == -1 and any(
            k in field_clean for k in ["date", "time", "trans_date"]
        ):
            date_idx = idx
        elif amount_idx == -1 and any(
            k in field_clean for k in ["amount", "value", "sum", "price", "charge"]
        ):
            amount_idx = idx
        elif desc_idx == -1 and any(
            k in field_clean
            for k in ["desc", "payee", "memo", "details", "narrative", "merchant"]
        ):
            desc_idx = idx

    return date_idx, amount_idx, desc_idx


def parse_expense_csv(
    path: Path, rules: Dict[str, List[str]]
) -> Tuple[List[Dict[str, Any]], Tuple[int, int, int]]:
    """Parse raw transaction bank-export CSV into normalized dictionaries.

    Args:
        path: Path to the target CSV file.
        rules: Categorization keyword rules.

    Returns:
        Tuple containing:
        - List of normalized transactions.
        - Tuple of detected column indices (date, amount, description).
    """
    # pylint: disable=too-many-locals
    transactions = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(2048)
            f.seek(0)
            dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
            reader = csv.reader(f, dialect)
            rows = list(reader)
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to parse CSV file %s: %s", path.name, err)
        return [], (-1, -1, -1)

    if not rows:
        return [], (-1, -1, -1)

    header = [col.strip().lower() for col in rows[0]]
    date_idx, amount_idx, desc_idx = detect_columns(header)

    # If column mappings failed, fallback to columns 0, 1, 2
    if date_idx == -1:
        date_idx = 0
    if amount_idx == -1:
        amount_idx = 1 if len(header) > 1 else 0
    if desc_idx == -1:
        desc_idx = 2 if len(header) > 2 else 0

    logger.debug(
        "Column mapping: Date=%d, Amount=%d, Desc=%d", date_idx, amount_idx, desc_idx
    )

    for row_num, row in enumerate(rows[1:], 2):
        if not row or len(row) <= max(date_idx, amount_idx, desc_idx):
            continue

        raw_date = row[date_idx]
        raw_amount = row[amount_idx]
        raw_desc = row[desc_idx]

        parsed_dt = parse_date(raw_date)
        if not parsed_dt:
            logger.warning(
                "Row %d: Skipping due to invalid date: '%s'", row_num, raw_date
            )
            continue

        amount_val = parse_amount(raw_amount)
        category = categorize_transaction(raw_desc, rules)

        transactions.append(
            {
                "date": parsed_dt.strftime("%Y-%m-%d"),
                "amount": amount_val,
                "description": raw_desc.strip(),
                "category": category,
            }
        )

    return transactions, (date_idx, amount_idx, desc_idx)


def generate_summaries(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compile monthly category totals, savings rate, and income vs expense stats.

    Args:
        transactions: list of normalized transactions.

    Returns:
        Dictionary report summary.
    """
    monthly_stats: Dict[str, Dict[str, Any]] = collections.defaultdict(
        lambda: {
            "income": 0.0,
            "expense": 0.0,
            "categories": collections.defaultdict(float),
        }
    )


    for t in transactions:
        dt = datetime.datetime.strptime(t["date"], "%Y-%m-%d")
        month_key = dt.strftime("%Y-%m")
        amount = t["amount"]
        category = t["category"]

        if category == "Income" or amount > 0:
            # Positive amounts are income
            monthly_stats[month_key]["income"] += amount
        else:
            # Negative amounts are expenses
            expense_val = abs(amount)
            monthly_stats[month_key]["expense"] += expense_val
            monthly_stats[month_key]["categories"][category] += expense_val

    # Convert default dicts to regular dicts for output
    formatted_report = {}
    for month, stats in sorted(monthly_stats.items()):
        income = stats["income"]
        expense = stats["expense"]
        savings = income - expense
        savings_rate = (savings / income * 100) if income > 0 else 0.0

        formatted_report[month] = {
            "total_income": round(income, 2),
            "total_expense": round(expense, 2),
            "net_savings": round(savings, 2),
            "savings_rate_pct": round(savings_rate, 2),
            "category_expenses": {
                cat: round(val, 2) for cat, val in sorted(stats["categories"].items())
            },
        }

    return formatted_report


def print_terminal_summary(report: Dict[str, Any]) -> None:
    """Print transaction monthly report summary in clean terminal layout."""
    sys.stdout.write("\n=== Expense & Income Summary Report ===\n")
    for month, stats in sorted(report.items()):
        sys.stdout.write(f"\nMonth: {month}\n")
        sys.stdout.write(f"  Income:   ${stats['total_income']:,.2f}\n")
        sys.stdout.write(f"  Expense:  ${stats['total_expense']:,.2f}\n")
        sys.stdout.write(
            f"  Net Save: ${stats['net_savings']:,.2f} "
            f"({stats['savings_rate_pct']:.2f}%)\n"
        )
        sys.stdout.write("  Expenses by Category:\n")
        if not stats["category_expenses"]:
            sys.stdout.write("    No categorized expenses recorded.\n")
        for cat, val in stats["category_expenses"].items():
            sys.stdout.write(f"    - {cat:<20}: ${val:,.2f}\n")
    sys.stdout.write("\n========================================\n")


def main() -> None:
    """CLI execution entry point."""
    # pylint: disable=too-many-branches, too-many-statements
    parser = argparse.ArgumentParser(
        description=(
            "CLI Expense Parser — normalize bank-export CSVs "
            "and auto-categorize spending."
        )
    )

    parser.add_argument(
        "-i", "--input", required=True, type=Path, help="Input bank-export CSV file."
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="Output file path (CSV or JSON)."
    )
    parser.add_argument(
        "-r", "--rules", type=Path, help="Custom category rules JSON file path."
    )
    parser.add_argument(
        "--format",
        choices=["terminal", "csv", "json"],
        default="terminal",
        help="Output report format (default: terminal).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.input.exists():
        logger.error("Input file does not exist: %s", args.input.as_posix())
        sys.exit(1)

    # Load categorization rules
    rules = DEFAULT_RULES
    if args.rules:
        if args.rules.exists():
            try:
                with open(args.rules, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                logger.info("Loaded custom category rules from: %s", args.rules.name)
            except Exception as err:  # pylint: disable=broad-exception-caught
                logger.error("Failed to parse custom rules JSON: %s", err)
                sys.exit(1)
        else:
            logger.error("Rules file not found: %s", args.rules.as_posix())
            sys.exit(1)

    # Run parser pipeline
    transactions, _ = parse_expense_csv(args.input, rules)
    if not transactions:
        logger.warning("No valid transactions found in input CSV.")
        sys.exit(0)

    report = generate_summaries(transactions)

    # Handle output exports
    if args.output:
        suffix = args.output.suffix.lower()
        try:
            if suffix == ".json":
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(
                        {"transactions": transactions, "summary": report}, f, indent=2
                    )
            elif suffix == ".csv":
                with open(args.output, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["date", "amount", "description", "category"])
                    for t in transactions:
                        writer.writerow(
                            [t["date"], t["amount"], t["description"], t["category"]]
                        )
            else:
                # Default to saving terminal summary text
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write("=== Expense & Income Summary Report ===\n")
                    for month, stats in sorted(report.items()):
                        f.write(f"\nMonth: {month}\n")
                        f.write(f"  Income:   ${stats['total_income']:,.2f}\n")
                        f.write(f"  Expense:  ${stats['total_expense']:,.2f}\n")
                        f.write(
                            f"  Net Save: ${stats['net_savings']:,.2f} "
                            f"({stats['savings_rate_pct']:.2f}%)\n"
                        )

                        f.write("  Expenses by Category:\n")
                        for cat, val in stats["category_expenses"].items():
                            f.write(f"    - {cat:<20}: ${val:,.2f}\n")
            logger.info("Report output saved to: %s", args.output.as_posix())
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.error("Failed to write report output file: %s", err)
            sys.exit(1)
    else:
        # Default to printing terminal summary
        if args.format == "terminal":
            print_terminal_summary(report)
        elif args.format == "json":
            sys.stdout.write(json.dumps(report, indent=2))
        elif args.format == "csv":
            writer = csv.writer(sys.stdout)
            writer.writerow(
                ["month", "income", "expense", "net_save", "savings_rate_pct"]
            )
            for month, stats in sorted(report.items()):
                writer.writerow(
                    [
                        month,
                        stats["total_income"],
                        stats["total_expense"],
                        stats["net_savings"],
                        stats["savings_rate_pct"],
                    ]
                )


if __name__ == "__main__":
    main()

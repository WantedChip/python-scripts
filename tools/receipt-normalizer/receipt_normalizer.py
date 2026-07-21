#!/usr/bin/env python3
"""Receipt Normalizer.

Extracts structured details (merchant, date, currency, total, tax) from messy
receipt PDFs and text files and exports normalized CSV or JSON files.
"""

import argparse
import csv
import json
import os
import re
import sys
from typing import Any, Dict

# Optional pypdf
try:
    import pypdf

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


def extract_text(file_path: str) -> str:
    """Extract plain text from files depending on their extensions."""
    _, ext = os.path.splitext(file_path.lower())
    if ext == ".pdf":
        if not HAS_PYPDF:
            msg = (
                f"Warning: Skipped PDF parsing for '{file_path}' (pypdf not installed)."
            )
            print(msg, file=sys.stderr)
            return ""
        try:
            texts = []
            reader = pypdf.PdfReader(file_path)
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    texts.append(txt)
            return "\n".join(texts)
        except (OSError, ValueError) as e:
            print(f"Error reading PDF {file_path}: {e}", file=sys.stderr)
            return ""

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        print(f"Error reading text file {file_path}: {e}", file=sys.stderr)
        return ""


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def parse_receipt_text(text: str) -> Dict[str, Any]:
    """Parse receipt text and extract fields using regex and heuristics."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return {
            "merchant": "Unknown",
            "date": "Unknown",
            "total": 0.0,
            "currency": "USD",
            "tax": 0.0,
        }

    # 1. Merchant Heuristic (Look at top lines)
    merchant = "Unknown"
    merchant_keywords = [
        "store",
        "shop",
        "cafe",
        "restaurant",
        "market",
        "inc",
        "llc",
        "ltd",
        "co",
        "coffee",
        "baker",
    ]
    for line in lines[:5]:
        line_lower = line.lower()
        if re.search(r"^\d", line):
            continue
        if any(kw in line_lower for kw in merchant_keywords) or len(line) < 30:
            merchant = line
            break
    if merchant == "Unknown" and lines:
        first_line = lines[0]
        if len(first_line) < 40:
            merchant = first_line

    # 2. Date Heuristics
    date_str = "Unknown"
    months = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    date_patterns = [
        r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b",
        r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{4}\b",
        rf"\b\d{{1,2}}\s+{months}\s+\d{{4}}\b",
        rf"\b{months}\s+\d{{1,2}},\s+\d{{4}}\b",
    ]

    for pat in date_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            date_str = match.group(0)
            break

    # 3. Currency Heuristics
    currency = "USD"
    currency_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "zł": "PLN"}
    for sym, code in currency_map.items():
        if sym in text:
            currency = code
            break

    iso_match = re.search(r"\b(USD|EUR|GBP|JPY|CAD|AUD|PLN)\b", text)
    if iso_match:
        currency = iso_match.group(1)

    # 4. Total and Tax Heuristics
    all_amounts = []
    for val_str in re.findall(r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b", text):
        normalized = val_str.replace(",", "")
        if "." not in normalized and len(val_str) > 3 and val_str[-3] == ",":
            normalized = val_str.replace(".", "").replace(",", ".")
        try:
            all_amounts.append(float(normalized))
        except ValueError:
            pass

    total = 0.0
    total_match_found = False
    total_keywords = [
        r"\btotal\b",
        r"\bgrand\s+total\b",
        r"\bamount\s+due\b",
        r"\bnet\s+payable\b",
        r"\btotal\s+amount\b",
    ]

    for kw in total_keywords:
        for line in lines:
            if re.search(kw, line.lower()):
                line_decimals = re.findall(
                    r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b", line
                )
                if line_decimals:
                    val_str = line_decimals[-1]
                    normalized = val_str.replace(",", "")
                    if (
                        "." not in normalized
                        and len(val_str) > 3
                        and val_str[-3] == ","
                    ):
                        normalized = val_str.replace(".", "").replace(",", ".")
                    try:
                        total = float(normalized)
                        total_match_found = True
                        break
                    except ValueError:
                        pass
        if total_match_found:
            break

    if not total_match_found and all_amounts:
        total = max(all_amounts)

    tax = 0.0
    tax_keywords = [r"\btax\b", r"\bvat\b", r"\bgst\b", r"\bsales\s+tax\b"]
    tax_match_found = False
    for kw in tax_keywords:
        for line in lines:
            if re.search(kw, line.lower()):
                line_decimals = re.findall(
                    r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b", line
                )
                if line_decimals:
                    val_str = line_decimals[-1]
                    normalized = val_str.replace(",", "")
                    if (
                        "." not in normalized
                        and len(val_str) > 3
                        and val_str[-3] == ","
                    ):
                        normalized = val_str.replace(".", "").replace(",", ".")
                    try:
                        tax = float(normalized)
                        tax_match_found = True
                        break
                    except ValueError:
                        pass
        if tax_match_found:
            break

    return {
        "merchant": merchant,
        "date": date_str,
        "total": total,
        "currency": currency,
        "tax": tax,
    }


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    desc = "Extract fields from receipts and output normalized CSV/JSON structures."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Receipt files or folders containing receipt scans (PDFs or text files).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to output file. Outputs JSON or CSV depending on extension.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["csv", "json"],
        default="csv",
        help=(
            "Explicit output format to use if --output is not specified "
            "(default: csv)."
        ),
    )

    args = parser.parse_args()

    files_to_process = []
    for inp in args.inputs:
        if os.path.isdir(inp):
            for root, _, files in os.walk(inp):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in (".pdf", ".txt", ".log"):
                        files_to_process.append(os.path.join(root, f))
        elif os.path.isfile(inp):
            files_to_process.append(inp)

    if not files_to_process:
        print("Error: No valid receipt files found to process.", file=sys.stderr)
        sys.exit(1)

    print(f"Normalizing {len(files_to_process)} receipt files...")
    normalized_records = []

    for fpath in files_to_process:
        text = extract_text(fpath)
        record = parse_receipt_text(text)
        record["file_source"] = os.path.abspath(fpath)
        normalized_records.append(record)
        b_name = os.path.basename(fpath)
        m_name = record["merchant"]
        c_code = record["currency"]
        t_amt = record["total"]
        msg = f"  Processed: {b_name} -> {m_name} ({c_code} {t_amt:.2f})"
        print(msg)

    out_format = args.format
    if args.output:
        _, ext = os.path.splitext(args.output.lower())
        if ext == ".json":
            out_format = "json"
        elif ext == ".csv":
            out_format = "csv"

    if args.output:
        try:
            if out_format == "json":
                with open(args.output, "w", encoding="utf-8") as out_f:
                    json.dump(normalized_records, out_f, indent=4)
            else:
                with open(args.output, "w", encoding="utf-8", newline="") as out_f:
                    headers = [
                        "file_source",
                        "merchant",
                        "date",
                        "currency",
                        "total",
                        "tax",
                    ]
                    writer = csv.DictWriter(out_f, fieldnames=headers)
                    writer.writeheader()
                    for rec in normalized_records:
                        writer.writerow(rec)
            msg = (
                f"Successfully wrote {len(normalized_records)} normalized records "
                f"to {args.output}"
            )
            print(msg)
        except OSError as e:
            print(f"Error saving output: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        if out_format == "json":
            print(json.dumps(normalized_records, indent=4))
        else:
            headers = ["file_source", "merchant", "date", "currency", "total", "tax"]
            writer = csv.DictWriter(sys.stdout, fieldnames=headers)
            writer.writeheader()
            for rec in normalized_records:
                writer.writerow(rec)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Data Peek.

Provides a unified previewer for CSV, TSV, JSON, JSONL, SQLite, and Excel/Parquet
files, detailing schemas, row counts, null values, samples, and column statistics.
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
from typing import Dict, List

# Optional modules
try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# pylint: disable=too-many-locals,too-many-branches
# pylint: disable=too-many-statements,too-many-nested-blocks
def peek_csv_tsv(file_path: str, delimiter: str = ",") -> None:
    """Analyze and output statistics for CSV/TSV data files."""
    print(f"Format Sniffed: {'TSV' if delimiter == '\t' else 'CSV'}")

    headers: List[str] = []
    row_count = 0
    sample_rows: List[List[str]] = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                headers = next(reader)
            except StopIteration:
                print("[-] Empty file.")
                return

            for row in reader:
                row_count += 1
                if len(sample_rows) < 5:
                    sample_rows.append(row)
    except (OSError, ValueError, csv.Error) as e:
        print(f"[-] Error reading file: {e}", file=sys.stderr)
        return

    print(f"Row Count (excluding header): {row_count}")
    print(f"Columns Count: {len(headers)}")
    print("-" * 80)
    fmt_head = (
        f"{'COLUMN NAME':<25} | {'INFERRED TYPE':<15} | {'NULL COUNT (%)':<15} | "
        f"{'SAMPLE VALUE'}"
    )
    print(fmt_head)
    print("-" * 80)

    for col_idx, col_name in enumerate(headers):
        null_count = 0
        val_types = set()
        sample_val = "N/A"

        for s_row in sample_rows:
            if col_idx < len(s_row):
                val = s_row[col_idx].strip()
                if not val:
                    null_count += 1
                else:
                    sample_val = val
                    if val.lower() in ("true", "false"):
                        val_types.add("bool")
                    else:
                        try:
                            int(val)
                            val_types.add("int")
                        except ValueError:
                            try:
                                float(val)
                                val_types.add("float")
                            except ValueError:
                                val_types.add("str")
            else:
                null_count += 1

        inferred = "str"
        if len(val_types) == 1:
            inferred = list(val_types)[0]
        elif "float" in val_types and "int" in val_types:
            inferred = "float"

        null_percent = (null_count / len(sample_rows) * 100) if sample_rows else 0.0
        line_out = (
            f"{col_name[:25]:<25} | {inferred:<15} | {null_count} "
            f"({null_percent:.1f}%) | {sample_val[:20]}"
        )
        print(line_out)


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def peek_json(file_path: str) -> None:
    """Analyze and output statistics for JSON or JSONL files."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()

            is_jsonl = False
            try:
                json.loads(first_line)
                second_line = f.readline().strip()
                if second_line:
                    json.loads(second_line)
                    is_jsonl = True
            except (json.JSONDecodeError, OSError):
                pass

            f.seek(0)
            if is_jsonl:
                print("Format Sniffed: JSONL (JSON Lines)")
                records = []
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            else:
                print("Format Sniffed: JSON")
                data = json.load(f)
                if isinstance(data, list):
                    records = data
                else:
                    records = [data]
    except (json.JSONDecodeError, OSError) as e:
        print(f"[-] Error parsing JSON: {e}", file=sys.stderr)
        return

    print(f"Total Records: {len(records)}")
    if not records:
        print("[-] No records to inspect.")
        return

    keys_counts: Dict[str, int] = {}
    keys_types: Dict[str, str] = {}
    sample_vals: Dict[str, str] = {}

    for r in records:
        if isinstance(r, dict):
            for k, v in r.items():
                keys_counts[k] = keys_counts.get(k, 0) + 1
                if v is not None and v != "":
                    tname = type(v).__name__
                    keys_types[k] = tname
                    sample_vals[k] = str(v)

    print("-" * 80)
    fmt_head = (
        f"{'FIELD NAME':<25} | {'INFERRED TYPE':<15} | {'NULL COUNT (%)':<15} | "
        f"{'SAMPLE VALUE'}"
    )
    print(fmt_head)
    print("-" * 80)

    for k in sorted(keys_counts.keys()):
        count = keys_counts[k]
        null_count = len(records) - count
        null_percent = null_count / len(records) * 100
        tname = keys_types.get(k, "null")
        sample_val = sample_vals.get(k, "N/A")
        line_out = (
            f"{k[:25]:<25} | {tname:<15} | {null_count} ({null_percent:.1f}%) | "
            f"{sample_val[:20]}"
        )
        print(line_out)


def peek_sqlite(file_path: str) -> None:
    """Analyze and output schemas for SQLite database files."""
    print("Format Sniffed: SQLite Database")
    try:
        conn = sqlite3.connect(file_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        print(f"Tables Found ({len(tables)}): {', '.join(tables)}")

        for table in tables:
            print("\n" + "=" * 80)
            print(f"TABLE Schema: {table}")
            print("=" * 80)

            cursor.execute(f"SELECT count(*) FROM {table}")  # nosec B608
            rows = cursor.fetchone()[0]
            print(f"Row count: {rows}")

            cursor.execute(f"PRAGMA table_info({table})")
            cols = cursor.fetchall()
            print("-" * 80)
            fmt_head = (
                f"{'CID':<5} | {'NAME':<25} | {'TYPE':<15} | "
                f"{'NOT NULL':<8} | {'PK':<5}"
            )
            print(fmt_head)
            print("-" * 80)
            for cid, name, ctype, notnull, _dflt, pk in cols:
                print(
                    f"{cid:<5} | {name[:25]:<25} | {ctype:<15} | {notnull:<8} | {pk:<5}"
                )
        conn.close()
    except sqlite3.Error as e:
        print(f"[-] SQLite connection error: {e}", file=sys.stderr)


def peek_pandas_formats(file_path: str, format_type: str) -> None:
    """Preview Excel or Parquet structures utilizing Pandas if installed."""
    if not HAS_PANDAS:
        print(
            "[-] Info: Previewing "
            f"{format_type} files requires pandas/openpyxl/pyarrow."
        )
        print("    Please run: pip install pandas openpyxl pyarrow")
        return

    print(f"Format Sniffed: {format_type} (using Pandas parser)")
    try:
        if format_type == "Excel":
            df = pd.read_excel(file_path, nrows=50)
        else:
            df = pd.read_parquet(file_path)

        print(f"Columns Count: {len(df.columns)}")
        print("-" * 80)
        fmt_head = (
            f"{'COLUMN NAME':<25} | {'DTYPE':<15} | {'NULLS (%)':<15} | "
            f"{'SAMPLE VALUE'}"
        )
        print(fmt_head)
        print("-" * 80)
        for col in df.columns:
            nulls = df[col].isnull().sum()
            null_pct = (nulls / len(df) * 100) if len(df) > 0 else 0.0
            sample_val = (
                str(df[col].dropna().iloc[0]) if not df[col].dropna().empty else "N/A"
            )
            line_out = (
                f"{str(col)[:25]:<25} | {str(df[col].dtype):<15} | {nulls} "
                f"({null_pct:.1f}%) | {sample_val[:20]}"
            )
            print(line_out)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"[-] Pandas read error: {e}", file=sys.stderr)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Unified file scanner inspecting schemas and sample records."
    )
    parser.add_argument(
        "file_path",
        help=(
            "Target data file path to analyze (CSV, TSV, JSON, JSONL, SQLite, "
            "XLSX, Parquet)."
        ),
    )

    args = parser.parse_args()

    fpath = os.path.abspath(args.file_path)
    if not os.path.exists(fpath):
        print(f"Error: File not found: {fpath}", file=sys.stderr)
        sys.exit(1)

    size_bytes = os.path.getsize(fpath)
    print("========================================================================")
    print("DATA PEEK: UNIFIED SCHEMAS DETECTOR")
    print("========================================================================")
    print(f"Target Path: {fpath}")
    print(f"File Size:   {size_bytes:,} bytes")
    print("-" * 80)

    ext = os.path.splitext(fpath)[1].lower()

    if ext == ".tsv":
        peek_csv_tsv(fpath, delimiter="\t")
    elif ext == ".csv":
        peek_csv_tsv(fpath, delimiter=",")
    elif ext in (".json", ".jsonl"):
        peek_json(fpath)
    elif ext in (".db", ".sqlite", ".sqlite3"):
        peek_sqlite(fpath)
    elif ext in (".xlsx", ".xls"):
        peek_pandas_formats(fpath, "Excel")
    elif ext in (".parquet", ".pq"):
        peek_pandas_formats(fpath, "Parquet")
    else:
        try:
            with open(fpath, "rb") as f:
                sig = f.read(15)
                if sig.startswith(b"SQLite format 3"):
                    peek_sqlite(fpath)
                    sys.exit(0)
        except OSError:
            pass

        print(
            "[-] Unrecognized file extension. Try parsing as standard text formats..."
        )
        peek_csv_tsv(fpath)


if __name__ == "__main__":
    main()

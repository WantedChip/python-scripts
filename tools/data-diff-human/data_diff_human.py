#!/usr/bin/env python3
"""Data Diff Human.

Compares JSON or CSV files using a key-based matching algorithm and outputs
a natural language summary of changes instead of raw diff dumps.
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple


def load_data(file_path: str) -> List[Dict[str, Any]]:
    """Load JSON (array or JSON lines) or CSV file into a list of dictionaries."""
    records: List[Dict[str, Any]] = []

    # Try JSON
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content.startswith("["):
                records = json.loads(content)
            else:
                # Try JSON Lines
                for line in content.splitlines():
                    if line.strip():
                        records.append(json.loads(line))
        return records
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    # Try CSV
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(2048)
            f.seek(0)
            delimiter = ","
            if sample:
                counts = {
                    ",": sample.count(","),
                    ";": sample.count(";"),
                    "\t": sample.count("\t"),
                }
                best_delim = max(counts, key=lambda k: counts[k])
                if counts[best_delim] > 0:
                    delimiter = best_delim

            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                records.append(dict(row))
        return records
    except (OSError, ValueError, csv.Error) as e:
        print(f"Error loading {file_path}: {e}", file=sys.stderr)
        sys.exit(1)


# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def compare_records(
    records1: List[Dict[str, Any]],
    records2: List[Dict[str, Any]],
    key_field: str,
    numeric_cols: Set[str],
    exclude_cols: Set[str],
    tolerance: float,
) -> Dict[str, Any]:
    """Compare two sets of records by primary key, calculating changes."""
    map1 = {str(r.get(key_field)): r for r in records1 if r.get(key_field) is not None}
    map2 = {str(r.get(key_field)): r for r in records2 if r.get(key_field) is not None}

    keys1 = set(map1.keys())
    keys2 = set(map2.keys())

    added_keys = keys2 - keys1
    removed_keys = keys1 - keys2
    common_keys = keys1 & keys2

    modified_count = 0
    column_modifications: Dict[str, List[Tuple[Any, Any, float, float]]] = defaultdict(
        list
    )
    text_modifications: Dict[str, List[Tuple[Any, Any]]] = defaultdict(list)

    for k in common_keys:
        r1 = map1[k]
        r2 = map2[k]

        row_changed = False
        all_fields = (set(r1.keys()) | set(r2.keys())) - exclude_cols - {key_field}

        for field in all_fields:
            v1 = r1.get(field)
            v2 = r2.get(field)

            if v1 == v2:
                continue

            is_numeric = False
            n1, n2 = None, None
            if field in numeric_cols:
                is_numeric = True
            else:
                try:
                    if v1 is not None and v2 is not None:
                        n1 = float(str(v1).replace(",", ""))
                        n2 = float(str(v2).replace(",", ""))
                        is_numeric = True
                    elif v1 is None and v2 is not None:
                        n1 = 0.0
                        n2 = float(str(v2).replace(",", ""))
                        is_numeric = True
                    elif v1 is not None and v2 is None:
                        n1 = float(str(v1).replace(",", ""))
                        n2 = 0.0
                        is_numeric = True
                except ValueError:
                    pass

            if is_numeric:
                if n1 is None:
                    try:
                        n1 = float(str(v1).replace(",", "")) if v1 else 0.0
                    except ValueError:
                        n1 = 0.0
                if n2 is None:
                    try:
                        n2 = float(str(v2).replace(",", "")) if v2 else 0.0
                    except ValueError:
                        n2 = 0.0

                diff = n2 - n1
                pct_diff = (
                    (diff / n1 * 100.0) if n1 != 0 else (100.0 if diff != 0 else 0.0)
                )

                if abs(pct_diff) > tolerance:
                    column_modifications[field].append((n1, n2, diff, pct_diff))
                    row_changed = True
            else:
                text_modifications[field].append((v1, v2))
                row_changed = True

        if row_changed:
            modified_count += 1

    return {
        "added": len(added_keys),
        "removed": len(removed_keys),
        "modified": modified_count,
        "numeric_changes": dict(column_modifications),
        "text_changes": dict(text_modifications),
    }


def generate_human_summary(diff_report: Dict[str, Any]) -> str:
    """Generate a clean, natural-language executive summary of the changes."""
    summary_parts = []

    overview = []
    if diff_report["added"] > 0:
        overview.append(f"{diff_report['added']:,} rows added")
    if diff_report["removed"] > 0:
        overview.append(f"{diff_report['removed']:,} records disappeared")
    if diff_report["modified"] > 0:
        overview.append(f"{diff_report['modified']:,} records modified")

    if not overview:
        return "No changes detected. The datasets are identical."

    summary_parts.append("Executive Summary: " + ", ".join(overview) + ".")

    num_changes = diff_report["numeric_changes"]
    text_changes = diff_report["text_changes"]

    if num_changes or text_changes:
        summary_parts.append("\nDetailed Changes:")

    for col, changes in num_changes.items():
        total_changed = len(changes)
        increases = [c for c in changes if c[2] > 0]
        decreases = [c for c in changes if c[2] < 0]

        avg_diff = sum(c[2] for c in changes) / total_changed
        avg_pct = sum(c[3] for c in changes) / total_changed

        summary_parts.append(
            f"  - Column '{col}': {total_changed:,} values modified "
            f"({len(increases):,} increased, {len(decreases):,} decreased). "
            f"Average change: {avg_diff:+.2f} ({avg_pct:+.1f}%)."
        )

    for col, changes in text_changes.items():
        total_changed = len(changes)
        changes_freq: Dict[str, int] = defaultdict(int)
        for v1, v2 in changes:
            changes_freq[f"'{v1}' -> '{v2}'"] += 1

        sorted_changes = sorted(changes_freq.items(), key=lambda x: x[1], reverse=True)
        top_examples = [f"{ch} ({cnt} times)" for ch, cnt in sorted_changes[:3]]
        top_str = ", ".join(top_examples)

        summary_parts.append(
            f"  - Column '{col}': {total_changed:,} text values changed. "
            f"Top transitions: {top_str}."
        )

    return "\n".join(summary_parts)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare two huge CSV or JSON files and output a clean, "
            "human-readable summary of differences."
        )
    )
    parser.add_argument("file1", help="Path to original data file (CSV or JSON).")
    parser.add_argument("file2", help="Path to modified data file (CSV or JSON).")
    parser.add_argument(
        "-k",
        "--key",
        required=True,
        help="Primary key column name used to match rows across files.",
    )
    parser.add_argument(
        "-n",
        "--numeric-cols",
        default="",
        help="Comma-separated list of column names to treat as numeric.",
    )
    parser.add_argument(
        "-t",
        "--tolerance",
        type=float,
        default=0.0,
        help="Allowable percent difference delta to ignore on numeric metrics.",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        default="",
        help="Comma-separated list of column names to exclude from comparison.",
    )

    args = parser.parse_args()

    records1 = load_data(args.file1)
    records2 = load_data(args.file2)

    numeric_set = {col.strip() for col in args.numeric_cols.split(",") if col.strip()}
    exclude_set = {col.strip() for col in args.exclude.split(",") if col.strip()}

    diff_results = compare_records(
        records1, records2, args.key, numeric_set, exclude_set, args.tolerance
    )

    human_summary = generate_human_summary(diff_results)
    print(human_summary)


if __name__ == "__main__":
    main()

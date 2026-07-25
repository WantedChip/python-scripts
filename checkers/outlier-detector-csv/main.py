"""Outlier Detector for CSV files.

Flags statistical outliers in numeric CSV columns using IQR (Interquartile Range)
or Z-score detection methods.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def calculate_percentile(sorted_values: List[float], percentile: float) -> float:
    """Calculate the p-th percentile of a sorted list using linear interpolation.

    Args:
        sorted_values: List of numeric values sorted in ascending order.
        percentile: Percentile value between 0.0 and 100.0.

    Returns:
        Interpolated percentile value.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower_idx = int(math.floor(rank))
    upper_idx = int(math.ceil(rank))
    weight = rank - lower_idx

    if upper_idx >= len(sorted_values):
        return sorted_values[-1]

    val_l = sorted_values[lower_idx]
    val_u = sorted_values[upper_idx]
    return val_l * (1.0 - weight) + val_u * weight


def detect_outliers_iqr(
    values: List[float], threshold: float = 1.5
) -> Tuple[List[bool], Dict[str, float]]:
    """Detect outliers using Interquartile Range (IQR) method.

    Args:
        values: List of numeric values.
        threshold: Multiplier for IQR (default 1.5 for mild outliers).

    Returns:
        Tuple containing a list of booleans (True if outlier) and summary stats dict.
    """
    if not values:
        return [], {}

    sorted_vals = sorted(values)
    q1 = calculate_percentile(sorted_vals, 25.0)
    q3 = calculate_percentile(sorted_vals, 75.0)
    iqr = q3 - q1
    lower_bound = q1 - (threshold * iqr)
    upper_bound = q3 + (threshold * iqr)

    is_outlier = [(v < lower_bound or v > upper_bound) for v in values]
    stats = {
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "median": statistics.median(values),
    }
    return is_outlier, stats


def detect_outliers_zscore(
    values: List[float], threshold: float = 3.0
) -> Tuple[List[bool], Dict[str, float], List[float]]:
    """Detect outliers using Z-score method.

    Args:
        values: List of float values.
        threshold: Absolute Z-score threshold (default 3.0).

    Returns:
        Tuple containing list of booleans, summary stats dict, and z-scores list.
    """
    if not values:
        return [], {}, []

    mean_val = statistics.mean(values)
    std_val = statistics.stdev(values) if len(values) > 1 else 0.0

    z_scores: List[float] = []
    is_outlier: List[bool] = []

    for v in values:
        if std_val == 0.0:
            z = 0.0
        else:
            z = (v - mean_val) / std_val
        z_scores.append(z)
        is_outlier.append(abs(z) > threshold)

    stats = {
        "mean": mean_val,
        "std_dev": std_val,
        "threshold": threshold,
    }
    return is_outlier, stats, z_scores


def process_csv(
    file_path: Path,
    target_columns: Optional[List[str]] = None,
    method: str = "iqr",
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Process CSV file and detect statistical outliers across columns.

    Args:
        file_path: Path to the input CSV file.
        target_columns: Optional list of column names to check.
        method: Outlier detection method ('iqr' or 'zscore').
        threshold: Threshold multiplier. Defaults to 1.5 for IQR and 3.0 for Z-score.

    Returns:
        Report dictionary containing summary and flagged outlier rows.
    """
    if threshold is None:
        threshold = 1.5 if method.lower() == "iqr" else 3.0

    with open(file_path, mode="r", encoding="utf-8", newline="") as f:
        reader = list(csv.DictReader(f))

    if not reader:
        return {
            "error": "CSV file is empty or missing headers.",
            "outliers": [],
            "summary": {},
        }

    available_cols = list(reader[0].keys())
    if target_columns:
        cols_to_check = [c for c in target_columns if c in available_cols]
    else:
        cols_to_check = available_cols

    summary_report: Dict[str, Any] = {}
    flagged_outliers: List[Dict[str, Any]] = []

    for col in cols_to_check:
        parsed_data: List[Tuple[int, float]] = []  # (row_index, numeric_value)
        for idx, row in enumerate(reader, start=1):
            raw_val = row.get(col, "")
            if raw_val is not None and raw_val.strip() != "":
                try:
                    num_val = float(raw_val.strip())
                    parsed_data.append((idx, num_val))
                except ValueError:
                    continue

        if not parsed_data:
            continue

        row_indices, values = zip(*parsed_data)
        values_list = list(values)

        if method.lower() == "iqr":
            is_outlier_list, stats = detect_outliers_iqr(
                values_list, threshold=threshold
            )
            z_scores_list = [0.0] * len(values_list)
        else:
            is_outlier_list, stats, z_scores_list = detect_outliers_zscore(
                values_list, threshold=threshold
            )

        outlier_count = sum(is_outlier_list)
        total_valid = len(values_list)

        summary_report[col] = {
            "total_rows": len(reader),
            "valid_numeric_rows": total_valid,
            "outlier_count": outlier_count,
            "outlier_percentage": (
                round((outlier_count / total_valid) * 100, 2) if total_valid else 0
            ),
            "stats": stats,
        }

        for i, is_out in enumerate(is_outlier_list):
            if is_out:
                row_idx = row_indices[i]
                val = values_list[i]
                record: Dict[str, Any] = {
                    "row_number": row_idx,
                    "column": col,
                    "value": val,
                    "method": method.lower(),
                    "threshold": threshold,
                }
                if method.lower() == "iqr":
                    lb = stats["lower_bound"]
                    ub = stats["upper_bound"]
                    diff = lb - val if val < lb else val - ub
                    record["bound_exceeded"] = "lower" if val < lb else "upper"
                    record["distance_from_bound"] = round(diff, 4)
                else:
                    record["z_score"] = round(z_scores_list[i], 4)

                flagged_outliers.append(record)

    return {
        "file": str(file_path),
        "method": method.lower(),
        "threshold": threshold,
        "summary": summary_report,
        "outliers": flagged_outliers,
    }


def print_report(report: Dict[str, Any]) -> None:
    """Print clean text report to stdout.

    Args:
        report: Dict returned by process_csv.
    """
    print("\n=== Outlier Detection Report ===")
    print(f"File: {report.get('file')}")
    m_str = report.get("method", "").upper()
    t_str = report.get("threshold")
    print(f"Method: {m_str} (Threshold: {t_str})\n")

    summary = report.get("summary", {})
    if not summary:
        print("No numeric columns evaluated.")
        return

    print("Column Summary:")
    hdr = f"{'Column':<20} | {'Total':<8} | {'Valid':<8} | {'Outliers':<9} | % Outliers"
    print(hdr)
    print("-" * 65)
    for col, stats in summary.items():
        row_s = (
            f"{col:<20} | {stats['total_rows']:<8} | "
            f"{stats['valid_numeric_rows']:<8} | "
            f"{stats['outlier_count']:<9} | {stats['outlier_percentage']}%"
        )
        print(row_s)

    outliers = report.get("outliers", [])
    print(f"\nFlagged Outliers Total: {len(outliers)}")
    if outliers:
        print("-" * 65)
        for item in outliers[:50]:  # Limit output preview to top 50
            if report.get("method") == "iqr":
                be = item["bound_exceeded"]
                db = item["distance_from_bound"]
                extra = f"bound={be}, dist={db}"
            else:
                extra = f"z_score={item.get('z_score')}"
            row_line = (
                f"Row {item['row_number']:<5} | Col: {item['column']:<15} | "
                f"Val: {item['value']:<10} | {extra}"
            )
            print(row_line)
        if len(outliers) > 50:
            print(f"... and {len(outliers) - 50} more outliers.")


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = "Flag statistical outliers in numeric CSV columns using IQR or Z-score."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("input_csv", type=Path, help="Path to input CSV file")
    parser.add_argument(
        "-c",
        "--column",
        nargs="+",
        help="Column name(s) to process. Defaults to all numeric columns.",
    )
    parser.add_argument(
        "-m",
        "--method",
        choices=["iqr", "zscore"],
        default="iqr",
        help="Outlier detection method: 'iqr' or 'zscore' (default: iqr)",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        help="Custom threshold value (default: 1.5 for IQR, 3.0 for Z-score)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Save report to specified output path (.json or .csv)",
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Outlier Detector."""
    parsed = parse_args(args)

    if not parsed.input_csv.exists():
        print(f"Error: File '{parsed.input_csv}' not found.", file=sys.stderr)
        return 1

    report = process_csv(
        file_path=parsed.input_csv,
        target_columns=parsed.column,
        method=parsed.method,
        threshold=parsed.threshold,
    )

    print_report(report)

    if parsed.output:
        parsed.output.parent.mkdir(parents=True, exist_ok=True)
        if parsed.output.suffix.lower() == ".json":
            with open(parsed.output, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        else:
            with open(parsed.output, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "row_number",
                        "column",
                        "value",
                        "method",
                        "threshold",
                        "bound_exceeded",
                        "distance_from_bound",
                        "z_score",
                    ],
                )
                writer.writeheader()
                for row in report.get("outliers", []):
                    writer.writerow(
                        {
                            "row_number": row.get("row_number"),
                            "column": row.get("column"),
                            "value": row.get("value"),
                            "method": row.get("method"),
                            "threshold": row.get("threshold"),
                            "bound_exceeded": row.get("bound_exceeded", ""),
                            "distance_from_bound": row.get("distance_from_bound", ""),
                            "z_score": row.get("z_score", ""),
                        }
                    )
        print(f"\nReport successfully saved to {parsed.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

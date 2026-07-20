#!/usr/bin/env python3
"""JSON Shape & Schema Drift Analyzer.

Analyzes structural formats, common/optional fields, and anomalies in JSON datasets.
"""

import argparse
import json
import sys
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple


# pylint: disable=too-many-branches
def get_nested_paths(data: Any, prefix: str = "") -> List[Tuple[str, str]]:
    """Recursively yield all nested paths and their types."""
    paths = []

    if isinstance(data, dict):
        if not data:
            paths.append((prefix, "empty_dict"))
        for k, v in data.items():
            sub_path = f"{prefix}.{k}" if prefix else k
            paths.extend(get_nested_paths(v, sub_path))
    elif isinstance(data, list):
        if not data:
            paths.append((prefix, "empty_list"))
        else:
            # We aggregate types inside the list under `path[]`
            sub_path = f"{prefix}[]"
            # Get types of all elements in the list
            for item in data:
                paths.extend(get_nested_paths(item, sub_path))
    else:
        # Base types
        if data is None:
            t = "null"
        elif isinstance(data, bool):
            t = "bool"
        elif isinstance(data, int):
            t = "int"
        elif isinstance(data, float):
            t = "float"
        elif isinstance(data, str):
            t = "str"
        else:
            t = type(data).__name__
        paths.append((prefix, t))

    return paths


# pylint: disable=too-many-locals
def analyze_records(records: List[Any]) -> Dict[str, Any]:
    """Analyze the collection of JSON records for schemas and anomalies."""
    total_records = len(records)
    if total_records == 0:
        return {"total_records": 0, "paths": {}, "anomalies": [], "schema_drift": []}

    # Map path -> type -> count of records in which this path has this type
    # (using record index to avoid double-counting lists elements)
    path_counts: Dict[str, Dict[str, Set[int]]] = defaultdict(lambda: defaultdict(set))
    path_presence: Dict[str, Set[int]] = defaultdict(set)

    for idx, record in enumerate(records):
        paths_in_record = get_nested_paths(record)
        for path, type_name in paths_in_record:
            path_presence[path].add(idx)
            path_counts[path][type_name].add(idx)

    # Compile metrics
    path_metrics = {}
    anomalies = []
    schema_drift = []

    for path, presence_set in path_presence.items():
        count = len(presence_set)
        frequency = count / total_records

        # Determine types and their occurrence rates
        types_info = {}
        for type_name, type_set in path_counts[path].items():
            types_info[type_name] = len(type_set)

        # Check for mixed types (excluding null / empty containers)
        non_null_types = [
            t for t in types_info if t not in ("null", "empty_dict", "empty_list")
        ]
        is_mixed = len(non_null_types) > 1

        path_metrics[path] = {
            "count": count,
            "frequency": frequency,
            "types": types_info,
            "is_mixed": is_mixed,
        }

        # Classify anomalies
        if is_mixed:
            anomalies.append(
                {
                    "path": path,
                    "issue": "Mixed types found",
                    "details": f"Types detected: {', '.join(non_null_types)}",
                }
            )

        # Schema drift / rare fields detection (< 5% frequency)
        if frequency < 0.05:
            schema_drift.append(
                {
                    "path": path,
                    "frequency": frequency,
                    "count": count,
                    "types": list(types_info.keys()),
                }
            )

    return {
        "total_records": total_records,
        "paths": path_metrics,
        "anomalies": anomalies,
        "schema_drift": schema_drift,
    }


# pylint: disable=too-many-locals,too-many-branches
def print_report(analysis: Dict[str, Any], show_all: bool) -> None:
    """Print a text report to stdout."""
    total = analysis["total_records"]
    print("========================================================================")
    print(f"JSON Shape Report (Total Records: {total})")
    print("========================================================================")

    paths_data = analysis["paths"]

    # Sort paths alphabetically
    sorted_paths = sorted(paths_data.keys())

    # Split fields by frequency
    required = []
    common = []
    optional = []
    rare = []

    for p in sorted_paths:
        freq = paths_data[p]["frequency"]
        types_str = ", ".join(f"{t}({c})" for t, c in paths_data[p]["types"].items())
        info = (p, f"{freq:.1%}", types_str)

        if freq >= 0.99:
            required.append(info)
        elif freq >= 0.90:
            common.append(info)
        elif freq >= 0.05:
            optional.append(info)
        else:
            rare.append(info)

    # Helper table printer
    def print_table(title: str, items: List[Tuple[str, str, str]]) -> None:
        if not items:
            return
        print(f"\n--- {title} ---")
        print(f"{'Path':<40} | {'Frequency':<10} | {'Types (Occurrences)':<20}")
        print("-" * 80)
        for path, freq, types in items:
            # Wrap long paths
            if len(path) > 38:
                print(f"{path[:35]}... | {freq:<10} | {types}")
            else:
                print(f"{path:<40} | {freq:<10} | {types}")

    print_table("Required Fields (>=99% presence)", required)
    print_table("Common Fields (90% - 99% presence)", common)

    if show_all or optional:
        print_table("Optional Fields (5% - 90% presence)", optional)

    if show_all or rare:
        print_table("Rare Fields / Schema Drift (<5% presence)", rare)

    # Print anomalies
    if analysis["anomalies"]:
        print("\n[!] ANOMALIES DETECTED")
        print("=" * 80)
        for idx, anomaly in enumerate(analysis["anomalies"], 1):
            print(f"{idx}. Path: {anomaly['path']}")
            print(f"   Issue: {anomaly['issue']}")
            print(f"   Details: {anomaly['details']}")
    else:
        print("\n[+] No type structural anomalies detected.")

    if analysis["schema_drift"]:
        print(
            f"\n[!] SCHEMA DRIFT DETECTED ({len(analysis['schema_drift'])} rare "
            "fields)"
        )
        print("-" * 80)
        for drift in analysis["schema_drift"][:10]:  # Limit to top 10
            print(
                f" - `{drift['path']}` (occurs in {drift['count']}/{total} records, "
                f"types: {drift['types']})"
            )
        if len(analysis["schema_drift"]) > 10:
            print(f" ... and {len(analysis['schema_drift']) - 10} more rare fields.")


# pylint: disable=too-many-branches
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Analyze structural layouts, optional/required fields, and type "
            "anomalies in JSON data."
        )
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="JSON file containing records. Reads from stdin if omitted.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Show all optional and rare fields in stdout table.",
    )
    parser.add_argument(
        "-j",
        "--json",
        help="Save full structured metrics analysis as JSON to specified path.",
    )

    args = parser.parse_args()

    # Load JSON records
    records: List[Any] = []
    raw_content = ""

    if args.input_file:
        try:
            with open(args.input_file, "r", encoding="utf-8") as f:
                raw_content = f.read()
        except OSError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        if not sys.stdin.isatty():
            raw_content = sys.stdin.read()

    raw_content = raw_content.strip()
    if not raw_content:
        parser.print_help()
        sys.exit(1)

    # Sniff structure (JSON Array vs JSON Lines)
    if raw_content.startswith("["):
        try:
            records = json.loads(raw_content)
            if not isinstance(records, list):
                records = [records]
        except json.JSONDecodeError as e:
            print(f"Invalid JSON Array format: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Try JSON Lines
        for line_num, line in enumerate(raw_content.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Invalid JSON Line {line_num}: {e}", file=sys.stderr)
                sys.exit(1)

    # Run analysis
    analysis_results = analyze_records(records)

    # Save JSON report if specified
    if args.json:
        try:
            # Convert Sets in results to list or counts for json encoding
            serializable_analysis = json.loads(
                json.dumps(analysis_results, default=list)
            )
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(serializable_analysis, f, indent=4)
            print(f"Successfully saved JSON metrics to {args.json}")
        except OSError as e:
            print(f"Error saving JSON analysis output: {e}", file=sys.stderr)
            sys.exit(1)

    # Print human report
    print_report(analysis_results, args.all)


if __name__ == "__main__":
    main()

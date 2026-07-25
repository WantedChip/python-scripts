"""JSON / JSONL to CSV Converter Utility.

Converts JSON object arrays or JSON lines (JSONL) files into CSV format.
Supports automatic column header collection (union of keys), nested object
flattening, list formatting, and custom delimiter options.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


def flatten_json_object(
    obj: Dict[str, Any], parent_key: str = "", sep: str = "."
) -> Dict[str, Any]:
    """Recursively flattens a nested dictionary into single-level key-value pairs.

    Args:
        obj: Dictionary object to flatten.
        parent_key: Prefix key for nested paths.
        sep: Separator between nested key levels.

    Returns:
        Flattened dictionary.
    """
    items: List[Tuple[str, Any]] = []
    for k, v in obj.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.extend(flatten_json_object(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            if not v:
                items.append((new_key, ""))
            elif all(not isinstance(elem, (dict, list)) for elem in v):
                items.append((new_key, ", ".join(map(str, v))))
            else:
                items.append((new_key, json.dumps(v)))
        else:
            items.append((new_key, "" if v is None else v))

    return dict(items)


def read_json_records(input_path: Path, is_jsonl: bool = False) -> List[Dict[str, Any]]:
    """Reads JSON or JSONL file into a list of record dictionaries.

    Args:
        input_path: Path to input JSON/JSONL file.
        is_jsonl: Explicitly treat file as JSON Lines format.

    Returns:
        List of raw records.
    """
    records: List[Dict[str, Any]] = []

    if is_jsonl or input_path.suffix.lower() == ".jsonl":
        with open(input_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        records.append(item)
    else:
        with open(input_path, "r", encoding="utf-8") as f:
            content = json.load(f)
            if isinstance(content, list):
                records = [rec for rec in content if isinstance(rec, dict)]
            elif isinstance(content, dict):
                records = [content]

    return records


def json_to_csv(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    is_jsonl: bool = False,
    flatten: bool = True,
    sep: str = ".",
    delimiter: str = ",",
) -> int:
    """Converts a JSON or JSONL file to a CSV file.

    Args:
        input_path: Path to input file.
        output_path: Path where CSV output will be saved.
        is_jsonl: Treat input as JSON Lines format.
        flatten: Flatten nested dictionary structures.
        sep: Separator for flattened header keys.
        delimiter: CSV field delimiter (e.g. ',', '\t', ';').

    Returns:
        Number of records converted.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    raw_records = read_json_records(input_path, is_jsonl=is_jsonl)
    if not raw_records:
        raise ValueError("No valid JSON records found in input file.")

    processed_records: List[Dict[str, Any]] = []
    headers: List[str] = []

    for rec in raw_records:
        flat_rec = flatten_json_object(rec, sep=sep) if flatten else rec
        processed_records.append(flat_rec)
        for key in flat_rec:
            if key not in headers:
                headers.append(key)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=headers, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(processed_records)

    return len(processed_records)


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    desc = "Convert JSON or JSONL files to CSV."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("input", help="Input JSON or JSONL file path")
    parser.add_argument("output", help="Output CSV file path")
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="Treat input strictly as JSON Lines (JSONL)",
    )
    parser.add_argument(
        "--no-flatten",
        action="store_true",
        help="Disable automatic flattening of nested objects",
    )
    parser.add_argument(
        "--sep",
        default=".",
        help="Key separator used for flattened headers (default: '.')",
    )
    parser.add_argument(
        "--delimiter",
        "-d",
        default=",",
        help="CSV column delimiter character (default: ',')",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for json-to-csv-converter."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    try:
        count = json_to_csv(
            input_path=parsed.input,
            output_path=parsed.output,
            is_jsonl=parsed.jsonl,
            flatten=not parsed.no_flatten,
            sep=parsed.sep,
            delimiter=parsed.delimiter,
        )
        msg = (
            f"Successfully converted {count} records from "
            f"'{parsed.input}' -> '{parsed.output}'."
        )
        print(msg)
    except (OSError, ValueError, json.JSONDecodeError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

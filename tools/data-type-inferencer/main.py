"""Data Type Inferencer CLI Tool.

Analyzes CSV columns, infers actual data types (integer, float, boolean,
datetime, json, enum, string), calculates null ratios and statistics,
and exports typed JSON schemas and converted CSV files.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-many-return-statements

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Boolean string literals
BOOL_TRUE_SET = {"true", "1", "yes", "y", "t"}
BOOL_FALSE_SET = {"false", "0", "no", "n", "f"}
BOOL_SET = BOOL_TRUE_SET | BOOL_FALSE_SET

# Common datetime regex patterns
DATE_PATTERNS = [
    re.compile(
        r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}"
        r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
    ),
    re.compile(r"^\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2}(?:\:\d{2})?)?$"),
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),
]


def is_integer(val_str: str) -> bool:
    """Check if string represents an integer.

    Args:
        val_str: String value.

    Returns:
        True if integer, False otherwise.
    """
    try:
        int(val_str)
        return True
    except ValueError:
        return False


def is_float(val_str: str) -> bool:
    """Check if string represents a floating point number.

    Args:
        val_str: String value.

    Returns:
        True if float, False otherwise.
    """
    try:
        float(val_str)
        return True
    except ValueError:
        return False


def is_boolean(val_str: str) -> bool:
    """Check if string represents a boolean value.

    Args:
        val_str: String value.

    Returns:
        True if boolean, False otherwise.
    """
    return val_str.strip().lower() in BOOL_SET


def is_datetime(val_str: str) -> bool:
    """Check if string represents a datetime value.

    Args:
        val_str: String value.

    Returns:
        True if datetime, False otherwise.
    """
    text = val_str.strip()
    for pattern in DATE_PATTERNS:
        if pattern.match(text):
            return True
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def is_json(val_str: str) -> bool:
    """Check if string represents a valid JSON object or array.

    Args:
        val_str: String value.

    Returns:
        True if JSON object/array, False otherwise.
    """
    text = val_str.strip()
    is_obj = text.startswith("{") and text.endswith("}")
    is_arr = text.startswith("[") and text.endswith("]")
    if not is_obj and not is_arr:
        return False
    try:
        json.loads(text)
        return True
    except (ValueError, TypeError):
        return False


def infer_single_value_type(val_str: str) -> str:
    """Infer data type for a single non-empty value.

    Args:
        val_str: Raw string value.

    Returns:
        Inferred type string: 'integer', 'float', 'boolean', 'datetime', etc.
    """
    text = val_str.strip()
    if not text:
        return "null"
    if is_boolean(text):
        return "boolean"
    if is_integer(text):
        return "integer"
    if is_float(text):
        return "float"
    if is_json(text):
        return "json"
    if is_datetime(text):
        return "datetime"
    return "string"


def analyze_column(
    col_name: str, values: List[str], max_enum_cardinality: int = 10
) -> Dict[str, Any]:
    """Analyze all sample values of a column to infer data type and schema.

    Args:
        col_name: Name of the column.
        values: List of string values for this column.
        max_enum_cardinality: Max distinct values count for enum inference.

    Returns:
        Dictionary containing column schema profile.
    """
    total_count = len(values)
    non_null_values = [v.strip() for v in values if v is not None and v.strip() != ""]
    null_count = total_count - len(non_null_values)
    null_ratio = (null_count / total_count) if total_count > 0 else 0.0

    if not non_null_values:
        return {
            "name": col_name,
            "inferred_type": "string",
            "nullable": True,
            "null_count": null_count,
            "null_ratio": round(null_ratio, 4),
            "distinct_count": 0,
            "sample_values": [],
        }

    distinct_values = sorted(list(set(non_null_values)))
    distinct_count = len(distinct_values)

    # Score candidate types
    type_counts: Dict[str, int] = {
        "boolean": 0,
        "integer": 0,
        "float": 0,
        "datetime": 0,
        "json": 0,
        "string": 0,
    }

    for val in non_null_values:
        t = infer_single_value_type(val)
        if t in type_counts:
            type_counts[t] += 1
        else:
            type_counts["string"] += 1

    total_non_null = len(non_null_values)

    # Determine dominant type
    if type_counts["boolean"] == total_non_null:
        inferred_type = "boolean"
    elif type_counts["integer"] == total_non_null:
        inferred_type = "integer"
    elif (type_counts["integer"] + type_counts["float"]) == total_non_null:
        inferred_type = "float"
    elif type_counts["datetime"] == total_non_null:
        inferred_type = "datetime"
    elif type_counts["json"] == total_non_null:
        inferred_type = "json"
    else:
        # Check if candidate for enum
        if distinct_count <= max_enum_cardinality and (
            total_non_null > distinct_count or distinct_count <= 5
        ):
            inferred_type = "enum"
        else:
            inferred_type = "string"

    result: Dict[str, Any] = {
        "name": col_name,
        "inferred_type": inferred_type,
        "nullable": null_count > 0,
        "null_count": null_count,
        "null_ratio": round(null_ratio, 4),
        "distinct_count": distinct_count,
        "sample_values": distinct_values[:5],
    }

    if inferred_type == "enum":
        result["enum_values"] = distinct_values

    return result


def convert_value_to_typed(val_str: str, target_type: str) -> Any:
    """Convert raw string value to typed Python representation.

    Args:
        val_str: Input value.
        target_type: Inferred data type.

    Returns:
        Converted value.
    """
    text = val_str.strip()
    if not text:
        return None

    if target_type == "boolean":
        return text.lower() in BOOL_TRUE_SET
    if target_type == "integer":
        try:
            return int(text)
        except ValueError:
            return text
    if target_type == "float":
        try:
            return float(text)
        except ValueError:
            return text
    if target_type == "json":
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return text
    return text


def process_dataset(
    input_file: Path,
    schema_output: Optional[Path] = None,
    converted_output: Optional[Path] = None,
    sample_size: int = 0,
    max_enum_cardinality: int = 10,
) -> Dict[str, Any]:
    """Process CSV file, infer column types, and generate schema & converted CSV.

    Args:
        input_file: Input CSV file path.
        schema_output: Path to export JSON schema.
        converted_output: Path to export converted typed CSV.
        sample_size: Number of rows to sample (0 for all rows).
        max_enum_cardinality: Max unique values threshold for enum inference.

    Returns:
        Dataset schema summary dictionary.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file non-existent: {input_file}")

    with input_file.open("r", encoding="utf-8-sig", newline="") as infile:
        reader = csv.reader(infile)
        rows = list(reader)

    if not rows:
        raise ValueError("Input CSV file is empty.")

    header = rows[0]
    data_rows = rows[1:]

    if sample_size > 0:
        data_rows = data_rows[:sample_size]

    # Organize values per column
    columns_data: Dict[str, List[str]] = {col: [] for col in header}
    for row in data_rows:
        for idx, col in enumerate(header):
            val = row[idx] if idx < len(row) else ""
            columns_data[col].append(val)

    # Analyze each column
    column_schemas = [
        analyze_column(
            col, columns_data[col], max_enum_cardinality=max_enum_cardinality
        )
        for col in header
    ]

    schema_result = {
        "dataset_name": input_file.name,
        "total_rows_analyzed": len(data_rows),
        "column_count": len(header),
        "columns": column_schemas,
    }

    if schema_output:
        schema_output.parent.mkdir(parents=True, exist_ok=True)
        with schema_output.open("w", encoding="utf-8") as f:
            json.dump(schema_result, f, indent=2)

    if converted_output:
        converted_output.parent.mkdir(parents=True, exist_ok=True)
        type_map = {col["name"]: col["inferred_type"] for col in column_schemas}

        output_rows = [header]
        for row in rows[1:]:
            if not row:
                continue
            converted_row = []
            for idx, col in enumerate(header):
                val = row[idx] if idx < len(row) else ""
                t = type_map[col]
                converted_val = convert_value_to_typed(val, t)
                val_str = "" if converted_val is None else str(converted_val)
                converted_row.append(val_str)
            output_rows.append(converted_row)

        with converted_output.open("w", encoding="utf-8", newline="") as outfile:
            writer = csv.writer(outfile)
            writer.writerows(output_rows)

    return schema_result


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Analyzes CSV columns and infers data types (integer, float, "
        "boolean, datetime, json, enum, string)."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-i",
        "--input-file",
        required=True,
        type=Path,
        help="Path to input CSV file",
    )
    parser.add_argument(
        "-s",
        "--schema-output",
        type=Path,
        help="Path to write output JSON schema profile",
    )
    parser.add_argument(
        "-c",
        "--converted-output",
        type=Path,
        help="Path to write converted typed CSV output",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=0,
        help="Number of rows to sample for inference (0 for all). Default: 0",
    )
    parser.add_argument(
        "--max-enum-cardinality",
        type=int,
        default=10,
        help="Maximum unique count threshold for enum type. Default: 10",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI execution flow."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    try:
        schema = process_dataset(
            input_file=parsed.input_file,
            schema_output=parsed.schema_output,
            converted_output=parsed.converted_output,
            sample_size=parsed.sample_size,
            max_enum_cardinality=parsed.max_enum_cardinality,
        )
        print(f"Data type inference complete for '{parsed.input_file.name}'.")
        print(f"Columns analyzed ({schema['column_count']}):")
        for col in schema["columns"]:
            msg = (
                f"  - {col['name']}: {col['inferred_type']} "
                f"(null ratio: {col['null_ratio']}, distinct: {col['distinct_count']})"
            )
            print(msg)

        if parsed.schema_output:
            print(f"JSON schema exported to: {parsed.schema_output}")
        if parsed.converted_output:
            print(f"Converted CSV exported to: {parsed.converted_output}")
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

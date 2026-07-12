"""Data Pipeline Diff Tool.

Compare two CSV/JSON/database outputs, identify additions, deletions,
and cell-level modifications with custom matching keys, numeric tolerances,
and exclusions. Generates Text, JSON, and HTML reports.
"""

# pylint: disable=too-many-lines, line-too-long

import argparse
import csv
import json
import logging
import math
import sqlite3
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("data_pipeline_diff")


@dataclass
class DiffResult:
    """Represents the complete diff results between two datasets."""

    # pylint: disable=too-many-instance-attributes

    headers_a: List[str]
    headers_b: List[str]
    added_columns: List[str]
    removed_columns: List[str]
    common_columns: List[str]
    total_rows_a: int
    total_rows_b: int
    keys: List[str]
    added_records: List[Dict[str, Any]]
    removed_records: List[Dict[str, Any]]
    # Maps record key (tuple of values) to list of field modifications
    # e.g., {("1",): [{"field": "age", "old": 30, "new": 31}]}
    modifications: Dict[Tuple[Any, ...], List[Dict[str, Any]]]
    identical_count: int


def setup_logging(verbose: bool) -> None:
    """Configure logger formatting and level.

    Args:
        verbose: Set log level to DEBUG if True, otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False


def flatten_data(val: Any, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """Recursively flattens a nested dictionary or list into a flat dictionary.

    Uses dot-notated paths for keys (e.g., {"user": {"name": "Bob"}} ->
    {"user.name": "Bob"}).

    Args:
        val: Nested dictionary, list, or primitive value.
        parent_key: Current accumulated path prefix.
        sep: Separator between path components.

    Returns:
        A dictionary with flattened paths mapped to primitive values.
    """
    items: List[Tuple[str, Any]] = []
    if isinstance(val, dict):
        for k, v in val.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, (dict, list)):
                items.extend(flatten_data(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
    elif isinstance(val, list):
        for i, v in enumerate(val):
            new_key = f"{parent_key}{sep}{i}" if parent_key else str(i)
            if isinstance(v, (dict, list)):
                items.extend(flatten_data(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
    else:
        items.append((parent_key, val))
    return dict(items)


def load_csv_source(filepath: Path, delimiter: str = ",") -> List[Dict[str, Any]]:
    """Loads a CSV file into a list of flat dictionaries.

    Args:
        filepath: Path to the CSV file.
        delimiter: CSV cell delimiter.

    Returns:
        List of row dictionaries.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        logger.warning(
            "UTF-8 decoding failed for %s. Falling back to latin-1.", filepath
        )
        with open(filepath, "r", encoding="latin-1") as f:
            content = f.read()

    reader = csv.DictReader(content.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError(f"CSV file {filepath} has no headers or is empty.")

    return [dict(row) for row in reader]


def load_json_source(filepath: Path) -> List[Dict[str, Any]]:
    """Loads a JSON file into a list of flat dictionaries.

    Flattens any nested dictionaries or lists on a per-row or per-object basis.

    Args:
        filepath: Path to the JSON file.

    Returns:
        List of dictionaries containing flat key-value pairs.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        rows: List[Dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                rows.append(flatten_data(item))
            else:
                rows.append(flatten_data(item))
        return rows
    if isinstance(data, dict):
        return [flatten_data(data)]

    raise ValueError("JSON must be a list of records or a dictionary object.")


def load_sqlite_source(
    db_path: Path, table: Optional[str] = None, query: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Loads SQLite rows or query results into flat dictionaries.

    Args:
        db_path: Path to the SQLite database.
        table: Table name to query.
        query: Custom SQL query to run.

    Returns:
        List of dictionaries representing database rows.
    """
    if not table and not query:
        raise ValueError(
            "Either table name or custom query must be provided for SQLite."
        )

    # sqlite3 requires string path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # Used implicitly for dict conversion
    # Reference for vulture whitelist
    _ = conn.row_factory
    cursor = conn.cursor()

    try:
        sql = query if query else f"SELECT * FROM {table}"  # nosec B608
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_source(
    filepath: Path,
    fmt: Optional[str] = None,
    delimiter: str = ",",
    table: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Helper to detect format and load a source.

    Args:
        filepath: Path to the file.
        fmt: Explicit format choice ('csv', 'json', 'sqlite').
        delimiter: CSV field delimiter.
        table: SQLite table name.
        query: SQLite custom SQL query.

    Returns:
        List of row dictionaries.
    """
    if not fmt:
        ext = filepath.suffix.lower()
        if ext == ".csv":
            fmt = "csv"
        elif ext == ".json":
            fmt = "json"
        elif ext in (".db", ".sqlite", ".sqlite3"):
            fmt = "sqlite"
        else:
            raise ValueError(
                f"Could not automatically detect format for file: {filepath}. "
                "Specify explicitly via --format."
            )

    if fmt == "csv":
        return load_csv_source(filepath, delimiter)
    if fmt == "json":
        return load_json_source(filepath)
    if fmt == "sqlite":
        return load_sqlite_source(filepath, table, query)

    raise ValueError(f"Unknown source format: {fmt}")


def auto_discover_keys(
    headers_a: List[str], headers_b: List[str]
) -> Optional[List[str]]:
    """Tries to find a common primary key candidate between two headers.

    Checks standard fields like 'id', 'uuid', 'pk', 'key' case-insensitively.

    Args:
        headers_a: Column list of first dataset.
        headers_b: Column list of second dataset.

    Returns:
        List of key columns if a unique candidate is found, otherwise None.
    """
    common = set(headers_a).intersection(set(headers_b))
    candidates = ["id", "uuid", "pk", "key", "id_"]
    for cand in candidates:
        for header in common:
            if header.lower() == cand:
                logger.info("Auto-discovered key column: '%s'", header)
                return [header]
    return None


def is_numeric_match(val1: Any, val2: Any, tolerance: float) -> bool:
    """Compares two cell values with float tolerance.

    Args:
        val1: First value.
        val2: Second value.
        tolerance: Absolute numeric threshold.

    Returns:
        True if they match exactly or within tolerance, False otherwise.
    """
    if val1 == val2:
        return True
    try:
        # Convert floats/ints or string representations of numeric types
        f1 = float(val1)
        f2 = float(val2)
        if math.isnan(f1) and math.isnan(f2):
            return True
        return abs(f1 - f2) <= tolerance
    except (ValueError, TypeError):
        return False


def compare_datasets(
    data1: List[Dict[str, Any]],
    data2: List[Dict[str, Any]],
    keys: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    tolerance: float = 0.0,
) -> DiffResult:
    """Core comparison function to calculate the diff between two datasets.

    Args:
        data1: List of dicts representing source A.
        data2: List of dicts representing source B.
        keys: Unique identifier column name(s).
        exclude: Columns/fields to ignore.
        tolerance: Floating point tolerance.

    Returns:
        DiffResult holding added/removed columns, rows, cell modifications, etc.
    """
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    exclude_set = set(exclude) if exclude else set()

    # Determine headers based on union of keys across all rows
    headers_a_set: Set[str] = set()
    for row in data1:
        headers_a_set.update(row.keys())
    headers_b_set: Set[str] = set()
    for row in data2:
        headers_b_set.update(row.keys())

    headers_a = sorted(list(headers_a_set))
    headers_b = sorted(list(headers_b_set))

    added_cols = sorted(list(headers_b_set - headers_a_set))
    removed_cols = sorted(list(headers_a_set - headers_b_set))
    common_cols = sorted(list(headers_a_set.intersection(headers_b_set)))

    # Handle key selection
    active_keys: List[str] = []
    if keys:
        active_keys = keys
    else:
        discovered = auto_discover_keys(headers_a, headers_b)
        if discovered:
            active_keys = discovered
        else:
            logger.info(
                "No primary key found or specified. Falling back to row indexes."
            )
            active_keys = ["__row_index__"]

    # Normalize datasets by injecting keys if using row indexes
    norm_data1 = data1
    norm_data2 = data2
    if active_keys == ["__row_index__"]:
        norm_data1 = []
        for i, row in enumerate(data1):
            norm_data1.append({"__row_index__": str(i), **row})
        norm_data2 = []
        for i, row in enumerate(data2):
            norm_data2.append({"__row_index__": str(i), **row})

    # Index datasets by key
    map_a: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in norm_data1:
        k_val = tuple(row.get(k) for k in active_keys)
        # Handle duplicated keys by warning
        if k_val in map_a:
            logger.warning("Duplicate key detected in Source A: %s", k_val)
        map_a[k_val] = row

    map_b: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in norm_data2:
        k_val = tuple(row.get(k) for k in active_keys)
        if k_val in map_b:
            logger.warning("Duplicate key detected in Source B: %s", k_val)
        map_b[k_val] = row

    keys_a = set(map_a.keys())
    keys_b = set(map_b.keys())

    added_keys = sorted(list(keys_b - keys_a))
    removed_keys = sorted(list(keys_a - keys_b))
    common_keys = sorted(list(keys_a.intersection(keys_b)))

    added_records = [map_b[k] for k in added_keys]
    removed_records = [map_a[k] for k in removed_keys]

    modifications: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    identical_count = 0

    # Compare common records
    all_compared_cols = (
        (headers_a_set.union(headers_b_set)) - set(active_keys) - exclude_set
    )

    for k in common_keys:
        row_a = map_a[k]
        row_b = map_b[k]
        row_mods = []

        for col in sorted(list(all_compared_cols)):
            # Handle missing keys on either side due to schema mismatch/
            # optional dict keys
            in_a = col in row_a
            in_b = col in row_b

            if in_a and in_b:
                val_a = row_a[col]
                val_b = row_b[col]
                if not is_numeric_match(val_a, val_b, tolerance):
                    row_mods.append({"field": col, "old": val_a, "new": val_b})
            elif in_a:
                row_mods.append({"field": col, "old": row_a[col], "new": None})
            elif in_b:
                row_mods.append({"field": col, "old": None, "new": row_b[col]})

        if row_mods:
            modifications[k] = row_mods
        else:
            identical_count += 1

    return DiffResult(
        headers_a=headers_a,
        headers_b=headers_b,
        added_columns=added_cols,
        removed_columns=removed_cols,
        common_columns=common_cols,
        total_rows_a=len(data1),
        total_rows_b=len(data2),
        keys=active_keys,
        added_records=added_records,
        removed_records=removed_records,
        modifications=modifications,
        identical_count=identical_count,
    )


def format_text_table(headers: List[str], rows: List[List[str]]) -> str:
    """Formats headers and rows into a clean text-based terminal table.

    Args:
        headers: Column title list.
        rows: Content matrix.

    Returns:
        Clean ASCII string table representation.
    """
    if not headers:
        return ""
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            if idx < len(widths):
                widths[idx] = max(widths[idx], len(str(cell)))

    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    header_str = (
        "|"
        + "|".join(
            f" {headers[idx].ljust(widths[idx])} " for idx in range(len(headers))
        )
        + "|"
    )

    row_strs = []
    for row in rows:
        row_str = (
            "|"
            + "|".join(
                (
                    f" {str(row[idx]).ljust(widths[idx])} "
                    if idx < len(row)
                    else " " * (widths[idx] + 2)
                )
                for idx in range(len(headers))
            )
            + "|"
        )
        row_strs.append(row_str)

    return "\n".join([border, header_str, border] + row_strs + [border])


def color_text(text: str, color_code: str, no_color: bool = False) -> str:
    """Applies ANSI styling codes to text.

    Args:
        text: Plain string.
        color_code: ANSI escape number (e.g. '31' for red).
        no_color: Disable styling if True.

    Returns:
        Formatted terminal string.
    """
    if no_color or not sys.stdout.isatty():
        return text
    return f"\033[{color_code}m{text}\033[0m"


def generate_text_report(
    res: DiffResult, no_color: bool = False, summary_only: bool = False
) -> str:
    """Builds a formatted terminal-ready textual summary of the diff results.

    Args:
        res: Completed DiffResult.
        no_color: Disable ANSI terminal coloring.
        summary_only: Skip individual row lists if True.

    Returns:
        Plain/styled multi-line string containing the report.
    """
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    lines = []
    lines.append("=" * 60)
    lines.append(" DATA PIPELINE DIFF REPORT")
    lines.append("=" * 60)

    # General Stats
    lines.append(f"Primary Keys Used: {', '.join(res.keys)}")
    lines.append(f"Source A Rows: {res.total_rows_a}")
    lines.append(f"Source B Rows: {res.total_rows_b}")
    lines.append("-" * 60)

    # Summary Metrics
    lines.append("CHANGE SUMMARY:")
    identical_str = f"  Identical Rows: {res.identical_count}"
    added_str = f"  Added Rows:     {len(res.added_records)}"
    removed_str = f"  Removed Rows:   {len(res.removed_records)}"
    modified_str = f"  Modified Rows:  {len(res.modifications)}"

    lines.append(color_text(identical_str, "34", no_color))  # Blue
    lines.append(color_text(added_str, "32", no_color))  # Green
    lines.append(color_text(removed_str, "31", no_color))  # Red
    lines.append(color_text(modified_str, "33", no_color))  # Yellow
    lines.append("-" * 60)

    # Schema Drift
    if res.added_columns or res.removed_columns:
        lines.append(color_text("SCHEMA DRIFT DETECTED:", "35", no_color))  # Magenta
        if res.added_columns:
            lines.append(f"  Added Columns:   {', '.join(res.added_columns)}")
        if res.removed_columns:
            lines.append(f"  Removed Columns: {', '.join(res.removed_columns)}")
        lines.append("-" * 60)

    if summary_only:
        return "\n".join(lines)

    # Detail Added
    if res.added_records:
        lines.append(color_text("ADDED RECORDS:", "32", no_color))
        # Compile headers for table
        tbl_headers = res.keys + [col for col in res.headers_b if col not in res.keys]
        tbl_rows = []
        for row in res.added_records[:20]:  # Limit console size
            tbl_rows.append([str(row.get(h, "")) for h in tbl_headers])
        lines.append(format_text_table(tbl_headers, tbl_rows))
        if len(res.added_records) > 20:
            lines.append(f"  ... and {len(res.added_records) - 20} more added records.")
        lines.append("-" * 60)

    # Detail Removed
    if res.removed_records:
        lines.append(color_text("REMOVED RECORDS:", "31", no_color))
        tbl_headers = res.keys + [col for col in res.headers_a if col not in res.keys]
        tbl_rows = []
        for row in res.removed_records[:20]:
            tbl_rows.append([str(row.get(h, "")) for h in tbl_headers])
        lines.append(format_text_table(tbl_headers, tbl_rows))
        if len(res.removed_records) > 20:
            lines.append(
                f"  ... and {len(res.removed_records) - 20} more removed records."
            )
        lines.append("-" * 60)

    # Detail Modified
    if res.modifications:
        lines.append(color_text("MODIFIED CELL DETAILS:", "33", no_color))
        tbl_headers = ["Record Key", "Field/Column", "Old Value", "New Value"]
        tbl_rows = []
        count = 0
        for r_key, mods in res.modifications.items():
            for mod in mods:
                if count < 50:  # Limit console rows
                    tbl_rows.append(
                        [
                            ", ".join(str(x) for x in r_key),
                            mod["field"],
                            str(mod["old"]),
                            str(mod["new"]),
                        ]
                    )
                    count += 1
        lines.append(format_text_table(tbl_headers, tbl_rows))
        total_mods = sum(len(m) for m in res.modifications.values())
        if total_mods > 50:
            lines.append(f"  ... and {total_mods - 50} more modified cells.")
        lines.append("-" * 60)

    return "\n".join(lines)


def generate_json_report(res: DiffResult) -> str:
    """Converts the DiffResult into a machine-readable JSON structure.

    Args:
        res: Completed DiffResult.

    Returns:
        Serialized JSON string.
    """
    # Key tuples must be mapped to string representation for valid JSON keys
    modified_serialized = {}
    for k, mods in res.modifications.items():
        key_str = ", ".join(str(x) for x in k)
        modified_serialized[key_str] = mods

    output = {
        "summary": {
            "total_rows_source_a": res.total_rows_a,
            "total_rows_source_b": res.total_rows_b,
            "identical_rows": res.identical_count,
            "added_rows": len(res.added_records),
            "removed_rows": len(res.removed_records),
            "modified_rows": len(res.modifications),
        },
        "schema_drift": {
            "added_columns": res.added_columns,
            "removed_columns": res.removed_columns,
            "common_columns": res.common_columns,
        },
        "keys_used": res.keys,
        "added_records": res.added_records,
        "removed_records": res.removed_records,
        "modified_details": modified_serialized,
    }
    return json.dumps(output, indent=2, default=str)


def generate_html_report(res: DiffResult, source_a: str, source_b: str) -> str:
    """Generates a professional and interactive single-file HTML diff report.

    Args:
        res: Completed DiffResult.
        source_a: Name/Path of Source A.
        source_b: Name/Path of Source B.

    Returns:
        Complete HTML document string.
    """
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    # Build Added table rows
    add_headers = res.keys + [c for c in res.headers_b if c not in res.keys]
    add_th = "".join(f"<th>{h}</th>" for h in add_headers)
    add_tr_list = []
    for r in res.added_records:
        tds = "".join(f"<td>{r.get(h, '')}</td>" for h in add_headers)
        add_tr_list.append(f"<tr class='added-row'>{tds}</tr>")
    add_rows_html = (
        "".join(add_tr_list) or "<tr><td colspan='100'>No rows added.</td></tr>"
    )

    # Build Removed table rows
    rem_headers = res.keys + [c for c in res.headers_a if c not in res.keys]
    rem_th = "".join(f"<th>{h}</th>" for h in rem_headers)
    rem_tr_list = []
    for r in res.removed_records:
        tds = "".join(f"<td>{r.get(h, '')}</td>" for h in rem_headers)
        rem_tr_list.append(f"<tr class='removed-row'>{tds}</tr>")
    rem_rows_html = (
        "".join(rem_tr_list) or "<tr><td colspan='100'>No rows removed.</td></tr>"
    )

    # Build Modifications table rows
    mod_tr_list = []
    for k, mods in res.modifications.items():
        key_str = ", ".join(str(x) for x in k)
        for mod in mods:
            mod_tr_list.append(
                f"<tr>"
                f"<td><strong>{key_str}</strong></td>"
                f"<td><span class='badge modified'>{mod['field']}</span></td>"
                f"<td><span class='old-val'>{mod['old']}</span></td>"
                f"<td><span class='new-val'>{mod['new']}</span></td>"
                f"</tr>"
            )
    mod_rows_html = (
        "".join(mod_tr_list) or "<tr><td colspan='4'>No rows modified.</td></tr>"
    )

    # Build Schema list
    schema_html_list = []
    if res.added_columns:
        added_badges = "".join(
            [f"<span class=badge added>{c}</span> " for c in res.added_columns]
        )
        schema_html_list.append(
            f"<li><strong>Added Columns:</strong> {added_badges}</li>"
        )
    if res.removed_columns:
        removed_badges = "".join(
            [f"<span class=badge removed>{c}</span> " for c in res.removed_columns]
        )
        schema_html_list.append(
            f"<li><strong>Removed Columns:</strong> {removed_badges}</li>"
        )
    if not res.added_columns and not res.removed_columns:
        schema_html_list.append("<li><em>No schema differences detected.</em></li>")
    schema_html = "".join(schema_html_list)

    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Data Pipeline Diff Report</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont,
                "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            color: #2D3748;
            background-color: #F7FAFC;
            margin: 0;
            padding: 2rem;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            font-size: 2rem;
            margin-bottom: 0.5rem;
            color: #1A202C;
        }}
        .meta {{
            font-size: 0.875rem;
            color: #718096;
            margin-bottom: 2rem;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background-color: #FFF;
            padding: 1.5rem;
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .card .value {{
            font-size: 1.75rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }}
        .card .label {{
            font-size: 0.875rem;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .card.identical {{ border-left: 4px solid #4A5568; }}
        .card.added {{ border-left: 4px solid #48BB78; color: #2F855A; }}
        .card.removed {{ border-left: 4px solid #F56565; color: #9B2C2C; }}
        .card.modified {{ border-left: 4px solid #ECC94B; color: #975A16; }}

        .tabs {{
            display: flex;
            border-bottom: 2px solid #E2E8F0;
            margin-bottom: 1.5rem;
        }}
        .tab {{
            padding: 0.75rem 1.5rem;
            cursor: pointer;
            font-weight: 600;
            color: #4A5568;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
        }}
        .tab.active {{
            color: #3182CE;
            border-bottom-color: #3182CE;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #FFF;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            border-radius: 0.5rem;
            overflow: hidden;
            margin-bottom: 2rem;
        }}
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid #E2E8F0;
        }}
        th {{
            background-color: #EDF2F7;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }}
        tr:hover {{
            background-color: #F7FAFC;
        }}
        .added-row {{ background-color: #F0FDF4; }}
        .removed-row {{ background-color: #FEF2F2; }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 700;
        }}
        .badge.added {{ background-color: #C6F6D5; color: #22543D; }}
        .badge.removed {{ background-color: #FED7D7; color: #742A2A; }}
        .badge.modified {{ background-color: #FEFCBF; color: #744210; }}

        .search-container {{
            margin-bottom: 1rem;
            display: flex;
            gap: 0.5rem;
        }}
        .search-input {{
            padding: 0.5rem 1rem;
            border: 1px solid #CBD5E0;
            border-radius: 0.25rem;
            flex-grow: 1;
            font-size: 0.875rem;
        }}
        .old-val {{
            text-decoration: line-through;
            color: #C53030;
            background-color: #FED7D7;
            padding: 0.125rem 0.25rem;
            border-radius: 0.125rem;
            margin-right: 0.5rem;
        }}
        .new-val {{
            color: #22543D;
            background-color: #C6F6D5;
            padding: 0.125rem 0.25rem;
            border-radius: 0.125rem;
        }}
        ul {{
            padding-left: 1.25rem;
            line-height: 1.75;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Data Pipeline Diff Report</h1>
        <div class="meta">
            Comparing <strong>A:</strong> {source_a} vs<br>
            <strong>B:</strong> {source_b}<br>
            Primary Keys: {", ".join(res.keys)}
        </div>

        <div class="stats-grid">
            <div class="card identical">
                <div class="value">{res.identical_count}</div>
                <div class="label">Identical</div>
            </div>
            <div class="card added">
                <div class="value">{len(res.added_records)}</div>
                <div class="label">Added</div>
            </div>
            <div class="card removed">
                <div class="value">{len(res.removed_records)}</div>
                <div class="label">Removed</div>
            </div>
            <div class="card modified">
                <div class="value">{len(res.modifications)}</div>
                <div class="label">Modified</div>
            </div>
        </div>

        <div class="tabs">
            <div class="tab active" onclick="switchTab('modified')">
                Modified Cells ({sum(len(m) for m in res.modifications.values())})
            </div>
            <div class="tab" onclick="switchTab('added')">
                Added Rows ({len(res.added_records)})
            </div>
            <div class="tab" onclick="switchTab('removed')">
                Removed Rows ({len(res.removed_records)})
            </div>
            <div class="tab" onclick="switchTab('schema')">Schema Drift</div>
        </div>

        <div id="modified" class="tab-content active">
            <div class="search-container">
                <input type="text" class="search-input" id="modSearch"
                    onkeyup="filterTable('modTable', 'modSearch')"
                    placeholder="Search modified cells...">
            </div>
            <table id="modTable">
                <thead>
                    <tr>
                        <th>Record Key</th>
                        <th>Field / Column</th>
                        <th>Old Value</th>
                        <th>New Value</th>
                    </tr>
                </thead>
                <tbody>
                    {mod_rows_html}
                </tbody>
            </table>
        </div>

        <div id="added" class="tab-content">
            <div class="search-container">
                <input type="text" class="search-input" id="addSearch"
                    onkeyup="filterTable('addTable', 'addSearch')"
                    placeholder="Search added rows...">
            </div>
            <table id="addTable">
                <thead>
                    <tr>
                        {add_th}
                    </tr>
                </thead>
                <tbody>
                    {add_rows_html}
                </tbody>
            </table>
        </div>

        <div id="removed" class="tab-content">
            <div class="search-container">
                <input type="text" class="search-input" id="remSearch"
                    onkeyup="filterTable('remTable', 'remSearch')"
                    placeholder="Search removed rows...">
            </div>
            <table id="remTable">
                <thead>
                    <tr>
                        {rem_th}
                    </tr>
                </thead>
                <tbody>
                    {rem_rows_html}
                </tbody>
            </table>
        </div>

        <div id="schema" class="tab-content">
            <h3>Schema Comparison</h3>
            <ul>
                {schema_html}
            </ul>
        </div>
    </div>

    <script>
        function switchTab(tabId) {{
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(c => c.classList.remove('active'));

            const tabs = document.querySelectorAll('.tab');
            tabs.forEach(t => t.classList.remove('active'));

            document.getElementById(tabId).classList.add('active');

            // Highlight active tab
            event.currentTarget.classList.add('active');
        }}

        function filterTable(tableId, inputId) {{
            const input = document.getElementById(inputId);
            const filter = input.value.toUpperCase();
            const table = document.getElementById(tableId);
            const trs = table.getElementsByTagName("tr");

            for (let i = 1; i < trs.length; i++) {{
                let show = false;
                const tds = trs[i].getElementsByTagName("td");
                for (let j = 0; j < tds.length; j++) {{
                    if (tds[j]) {{
                        const text = tds[j].textContent || tds[j].innerText;
                        if (text.toUpperCase().indexOf(filter) > -1) {{
                            show = true;
                            break;
                        }}
                    }}
                }}
                trs[i].style.display = show ? "" : "none";
            }}
        }}
    </script>
</body>
</html>
"""
    return html_template


def main() -> None:
    """Command line entry point parsing parameters and performing comparison."""
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements

    parser = argparse.ArgumentParser(
        description=(
            "Data Pipeline Diff Tool — compare two CSV/JSON/database outputs "
            "and explain exactly what changed."
        )
    )
    parser.add_argument(
        "source1",
        type=str,
        help="Path to first CSV/JSON/SQLite file.",
    )
    parser.add_argument(
        "source2",
        type=str,
        nargs="?",
        default=None,
        help=(
            "Path to second CSV/JSON/SQLite file. Optional if comparing "
            "tables within same SQLite database."
        ),
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["csv", "json", "sqlite"],
        help="Force input format. Otherwise auto-detected by extension.",
    )
    parser.add_argument(
        "-k",
        "--key",
        help="Comma-separated column/field names to use as the unique "
        "record matching key.",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        help="Comma-separated columns/fields to exclude from value comparison.",
    )
    parser.add_argument(
        "-t",
        "--tolerance",
        type=float,
        default=0.0,
        help="Absolute tolerance threshold for floating point matching.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Optional file path to write results.",
    )
    parser.add_argument(
        "--out-format",
        choices=["text", "json", "html"],
        default="text",
        help="Export format of report. Defaults to text.",
    )
    parser.add_argument(
        "-s",
        "--summary-only",
        action="store_true",
        help="Only display overall stats instead of cell level details in text output.",
    )
    parser.add_argument(
        "--delimiter",
        default=",",
        help="CSV delimiter. Default is comma.",
    )
    parser.add_argument(
        "--table",
        help="SQLite table name to compare (used when format is sqlite).",
    )
    parser.add_argument(
        "--table1",
        help="SQLite table name in source1 database.",
    )
    parser.add_argument(
        "--table2",
        help="SQLite table name in source2 database (or source1 "
        "if source2 not provided).",
    )
    parser.add_argument(
        "--query",
        help="SQLite SQL query to compare.",
    )
    parser.add_argument(
        "--query1",
        help="SQLite SQL query on source1 database.",
    )
    parser.add_argument(
        "--query2",
        help="SQLite SQL query on source2 database (or source1 "
        "if source2 not provided).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose debug logging.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Suppress ANSI colors in terminal outputs.",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        path1 = Path(args.source1)
        if not path1.exists():
            print(f"Error: source1 file '{path1}' not found.", file=sys.stderr)
            sys.exit(1)

        data1: List[Dict[str, Any]] = []
        data2: List[Dict[str, Any]] = []

        # Parse exclusions and keys
        exclude_list = (
            [x.strip() for x in args.exclude.split(",")] if args.exclude else []
        )
        key_list = [x.strip() for x in args.key.split(",")] if args.key else None

        # sqlite connection branching
        if args.format == "sqlite" or path1.suffix.lower() in (
            ".sqlite",
            ".db",
            ".sqlite3",
        ):
            tbl1 = args.table1 or args.table
            tbl2 = args.table2 or args.table
            qry1 = args.query1 or args.query
            qry2 = args.query2 or args.query

            if args.source2:
                path2 = Path(args.source2)
                if not path2.exists():
                    print(f"Error: source2 file '{path2}' not found.", file=sys.stderr)
                    sys.exit(1)
                data1 = load_sqlite_source(path1, tbl1, qry1)
                data2 = load_sqlite_source(path2, tbl2, qry2)
            else:
                # Comparing inside same database file
                if not tbl1 or not tbl2:
                    if not qry1 or not qry2:
                        print(
                            "Error: To compare within the same database, you "
                            "must specify either --table1 and --table2, or "
                            "--query1 and --query2.",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                data1 = load_sqlite_source(path1, tbl1, qry1)
                data2 = load_sqlite_source(path1, tbl2, qry2)
        else:
            if not args.source2:
                print("Error: Missing source2 file parameter.", file=sys.stderr)
                sys.exit(1)
            path2 = Path(args.source2)
            if not path2.exists():
                print(f"Error: source2 file '{path2}' not found.", file=sys.stderr)
                sys.exit(1)

            data1 = load_source(
                path1,
                args.format,
                args.delimiter,
                args.table1 or args.table,
                args.query1 or args.query,
            )
            data2 = load_source(
                path2,
                args.format,
                args.delimiter,
                args.table2 or args.table,
                args.query2 or args.query,
            )

        diff_res = compare_datasets(
            data1,
            data2,
            keys=key_list,
            exclude=exclude_list,
            tolerance=args.tolerance,
        )

        # Generate report
        report_content = ""
        if args.out_format == "text":
            report_content = generate_text_report(
                diff_res, no_color=args.no_color, summary_only=args.summary_only
            )
        elif args.out_format == "json":
            report_content = generate_json_report(diff_res)
        elif args.out_format == "html":
            report_content = generate_html_report(
                diff_res, str(path1), str(Path(args.source2) if args.source2 else path1)
            )

        # Print/save
        if args.output:
            out_path = Path(args.output)
            out_path.write_text(report_content, encoding="utf-8")
            print(f"Report written successfully to: {out_path}")
        else:
            print(report_content)

    except Exception as e:  # pylint: disable=broad-except
        print(f"Error executing pipeline diff: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

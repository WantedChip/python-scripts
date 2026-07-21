#!/usr/bin/env python3
"""Fixture Shrinker — Reduce a giant failing JSON, CSV, or text file.

Uses delta debugging and hierarchical pruning to find the smallest input
that still reproduces a bug by running a validation command.
"""

import argparse
import copy
import csv
import io
import json
import logging
import os
import shlex
import subprocess  # nosec B404 - used to run the validation command
import sys
from typing import Any, Callable, Dict, List, Optional

# Set up logger
logger = logging.getLogger("fixture_shrinker")


def setup_logging(verbose: bool) -> None:
    """Configure logger verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)


def run_validation(command: str, temp_file_path: str) -> bool:
    """Run the validation command and check if it fails (returns non-zero)."""
    cmd_str = command.replace("{}", temp_file_path)
    cmd_parts = shlex.split(cmd_str)

    try:
        res = subprocess.run(  # nosec B603
            cmd_parts,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        reproduced = res.returncode != 0
        logger.debug(
            "Validation run exit code: %d (reproduced: %s)",
            res.returncode,
            reproduced,
        )
        return reproduced
    except (subprocess.SubprocessError, FileNotFoundError) as err:
        logger.error("Failed to run validation command: %s", err)
        return False


def _update_dict(d: Dict[str, Any], k: str, v: Any) -> None:
    """Helper to update dictionary value in-place."""
    d[k] = v


def _update_list(lst: List[Any], idx: int, v: Any) -> None:
    """Helper to update list element in-place."""
    lst[idx] = v


def shrink_json_step(
    val: Any,
    validate_fn: Callable[[Any], bool],
    update_fn: Callable[[Any], None],
    parent_data: Any,
) -> Any:
    """Attempt to shrink a nested JSON structure and update its parent context."""
    if not isinstance(val, (dict, list, str, int, float)):
        return val

    original = val
    if isinstance(val, dict) and val:
        update_fn({})
        if validate_fn(parent_data):
            return {}
        update_fn(original)
    elif isinstance(val, list) and val:
        update_fn([])
        if validate_fn(parent_data):
            return []
        update_fn(original)

    val_copy = copy.deepcopy(val)

    def recursive_validate(v: Any) -> bool:
        update_fn(v)
        if validate_fn(parent_data):
            return True
        update_fn(original)
        return False

    shrunk = shrink_json(val_copy, recursive_validate)
    return shrunk


# pylint: disable=too-many-branches,too-many-statements,too-many-locals
def shrink_json(data: Any, validate_fn: Callable[[Any], bool]) -> Any:
    """Recursively prune JSON dictionary keys, list items, and reduce values."""
    changed = True
    while changed:
        changed = False
        if isinstance(data, dict):
            keys = list(data.keys())
            for key in keys:
                val = data.pop(key)
                if validate_fn(data):
                    changed = True
                    break
                data[key] = val
            if changed:
                continue

            for key, val in list(data.items()):

                def update_k(v: Any, k: str = key) -> None:
                    _update_dict(data, k, v)

                shrunk_val = shrink_json_step(val, validate_fn, update_k, data)
                if shrunk_val != val:
                    data[key] = shrunk_val
                    changed = True
                    break

        elif isinstance(data, list):
            n = len(data)
            if n > 1:
                mid = n // 2
                left = data[mid:]
                if validate_fn(left):
                    data = left
                    changed = True
                    continue
                right = data[:mid]
                if validate_fn(right):
                    data = right
                    changed = True
                    continue

                for i in range(n):
                    val = data.pop(i)
                    if validate_fn(data):
                        changed = True
                        break
                    data.insert(i, val)
                if changed:
                    continue

            for i, val in enumerate(data):

                def update_i(v: Any, idx: int = i) -> None:
                    _update_list(data, idx, v)

                shrunk_val = shrink_json_step(val, validate_fn, update_i, data)
                if shrunk_val != val:
                    data[i] = shrunk_val
                    changed = True
                    break

        elif isinstance(data, str) and data != "":
            if validate_fn(""):
                data = ""
                changed = True

        elif isinstance(data, (int, float)) and data != 0:
            if validate_fn(0):
                data = 0
                changed = True
            elif isinstance(data, int) and abs(data) > 1:
                for divisor in [10, 2]:
                    candidate = data // divisor
                    if validate_fn(candidate):
                        data = candidate
                        changed = True
                        break

    return data


# pylint: disable=too-many-nested-blocks
def shrink_csv(
    rows: List[List[str]],
    header: Optional[List[str]],
    validate_fn: Callable[[List[List[str]]], bool],
) -> List[List[str]]:
    """Prune CSV rows and columns using delta debugging."""
    changed = True
    while changed:
        changed = False
        n = len(rows)
        if n > 1:
            mid = n // 2
            left = rows[mid:]
            if validate_fn(left):
                rows = left
                changed = True
                continue
            right = rows[:mid]
            if validate_fn(right):
                rows = right
                changed = True
                continue

            for i in range(n):
                row = rows.pop(i)
                if validate_fn(rows):
                    changed = True
                    break
                rows.insert(i, row)
            if changed:
                continue

        if n > 0:
            num_cols = len(rows[0])
            if num_cols > 1:
                for col_idx in range(num_cols):
                    nxt = col_idx + 1
                    reduced = [r[:col_idx] + r[nxt:] for r in rows]
                    if validate_fn(reduced):
                        rows = reduced
                        if header:
                            header.pop(col_idx)
                        changed = True
                        break

    return rows


def shrink_text(
    lines: List[str], validate_fn: Callable[[List[str]], bool]
) -> List[str]:
    """Prune lines of a raw text payload."""
    changed = True
    while changed:
        changed = False
        n = len(lines)
        if n > 1:
            mid = n // 2
            left = lines[mid:]
            if validate_fn(left):
                lines = left
                changed = True
                continue
            right = lines[:mid]
            if validate_fn(right):
                lines = right
                changed = True
                continue

            for i in range(n):
                line = lines.pop(i)
                if validate_fn(lines):
                    changed = True
                    break
                lines.insert(i, line)
            if changed:
                continue

    return lines


def process_json(input_content: str, temp_path: str, command: str) -> str:
    """Parse, shrink, and return JSON content."""
    try:
        data = json.loads(input_content)
    except ValueError as err:
        logger.error("Failed to parse JSON content: %s", err)
        sys.exit(1)

    def validate(candidate: Any) -> bool:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(candidate, f)
        return run_validation(command, temp_path)

    if not validate(data):
        logger.error(
            "Initial input does not reproduce the bug (validation command passed)."
        )
        sys.exit(1)

    shrunk_data = shrink_json(data, validate)
    return json.dumps(shrunk_data, indent=2)


def process_csv(
    input_content: str, temp_path: str, command: str, has_header: bool
) -> str:
    """Parse, shrink, and return CSV content."""
    reader = csv.reader(input_content.splitlines())
    all_rows = list(reader)
    if not all_rows:
        return ""

    header = all_rows.pop(0) if has_header else None
    rows = all_rows

    def validate(candidate_rows: List[List[str]]) -> bool:
        with open(temp_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if header:
                writer.writerow(header)
            writer.writerows(candidate_rows)
        return run_validation(command, temp_path)

    if not validate(rows):
        logger.error(
            "Initial input does not reproduce the bug (validation command passed)."
        )
        sys.exit(1)

    shrunk_rows = shrink_csv(rows, header, validate)

    output_lines = []
    if header:
        output_lines.append(header)
    output_lines.extend(shrunk_rows)

    output_io = io.StringIO()
    writer = csv.writer(output_io)
    writer.writerows(output_lines)
    return output_io.getvalue()


def process_text(input_content: str, temp_path: str, command: str) -> str:
    """Prune raw text/API response line by line."""
    lines = input_content.splitlines()

    def validate(candidate_lines: List[str]) -> bool:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write("\n".join(candidate_lines))
        return run_validation(command, temp_path)

    if not validate(lines):
        logger.error(
            "Initial input does not reproduce the bug (validation command passed)."
        )
        sys.exit(1)

    shrunk_lines = shrink_text(lines, validate)
    return "\n".join(shrunk_lines)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "fixture-shrinker: Reduce large payloads to smallest reproducing input."
        )
    )
    parser.add_argument(
        "--input", required=True, help="Path to giant failing payload file"
    )
    parser.add_argument(
        "--command",
        required=True,
        help=(
            "Validation command to run (e.g. 'pytest tests/test_bug.py'). "
            "Use '{}' in command to substitute the minimized temp file path."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "text"],
        help="Payload format (auto-detected if omitted)",
    )
    parser.add_argument(
        "--output", required=True, help="Path to write minimized output payload"
    )
    parser.add_argument(
        "--has-header",
        action="store_true",
        help="Specify if CSV contains a header row to preserve",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable detailed logs"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not os.path.exists(args.input):
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        content = f.read()

    fmt = args.format
    if not fmt:
        if args.input.endswith(".json"):
            fmt = "json"
        elif args.input.endswith(".csv"):
            fmt = "csv"
        else:
            fmt = "text"

    temp_path = args.output + ".temp"

    try:
        if fmt == "json":
            result = process_json(content, temp_path, args.command)
        elif fmt == "csv":
            result = process_csv(content, temp_path, args.command, args.has_header)
        else:
            result = process_text(content, temp_path, args.command)

        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)

        logger.info("Successfully shrunk payload written to: %s", args.output)

    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


if __name__ == "__main__":
    main()

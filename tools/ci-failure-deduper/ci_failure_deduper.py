#!/usr/bin/env python3
"""CI Failure Deduper — Group multiple CI log failures by their root cause.

Analyzes log text, extracts traceback blocks or error messages, sanitizes
variable details (like hex memory addresses, line numbers, times, paths),
and groups the failures to help developers resolve issues efficiently.
"""

import argparse
import glob
import os
import re
import sys
from typing import Any, Dict, List, Tuple


def sanitize_message(message: str) -> str:
    """Sanitize dynamic parts of an error message to create a consistent key/template.

    Args:
        message: The raw error message string.

    Returns:
        The sanitized error message with placeholders.
    """
    # Replace hex addresses (e.g., 0x7f1a3b2c4d5e)
    message = re.sub(r"0x[0-9a-fA-F]+", "<hex_addr>", message)

    # Replace temp directory patterns (e.g., /tmp/pytest-of-user/pytest-0/...)
    message = re.sub(r"pytest-of-[a-zA-Z0-9_]+/pytest-\d+", "<pytest_tempdir>", message)

    # Replace filenames in Python tracebacks (e.g., File "filename.py", line X)
    message = re.sub(r'File "[^"]+"', 'File "<path>"', message)

    # Replace absolute file paths (Windows and Unix style)
    # Match strings containing slashes and typical file characters
    message = re.sub(
        r"(?:[a-zA-Z]:)?[\\/][a-zA-Z0-9_\.\-]+(?:[\\/][a-zA-Z0-9_\.\-]+)+",
        "<path>",
        message,
    )

    # Replace timestamp durations (e.g., "2026-07-16T09:47:47", "12.34s")
    message = re.sub(
        r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?\b",
        "<timestamp>",
        message,
    )
    message = re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:s|ms|seconds|seconds)\b", "<duration>", message
    )

    # Replace line numbers in file contexts (e.g., "line 123", "main.py:123")
    message = re.sub(r"\bline \d+\b", "line <line>", message)
    message = re.sub(r"\.py:\d+", ".py:<line>", message)
    message = re.sub(r":\d+:\d+", ":<line>:<col>", message)
    message = re.sub(r":\d+", ":<line>", message)

    # Replace numeric values (like ID numbers or counts)
    message = re.sub(r"\b\d+\b", "<num>", message)

    # Strip excessive whitespace
    message = " ".join(message.split())

    return message


def extract_python_traceback(lines: List[str], start_idx: int) -> Tuple[str, int]:
    """Extract a full Python traceback block.

    Args:
        lines: All log lines.
        start_idx: Index of line containing "Traceback (most recent call last):".

    Returns:
        A tuple of (extracted multiline traceback, next line index to process).
    """
    traceback_lines = []
    idx = start_idx
    # Append the traceback header
    traceback_lines.append(lines[idx])
    idx += 1

    # Keep scanning until we find a line that doesn't start with space,
    # and is not part of the traceback, but wait: the final exception message
    # line does NOT start with space! So we include lines starting with
    # spaces, plus the first non-indented line after them (which is the
    # exception name and message).
    has_seen_indented = False
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("    ") or line.startswith("\t") or 'File "' in line:
            traceback_lines.append(line)
            has_seen_indented = True
            idx += 1
        elif has_seen_indented:
            # This should be the exception type and message line (e.g. ValueError: ...)
            traceback_lines.append(line)
            idx += 1
            break
        else:
            # If we saw no indented lines but trace header,
            # it might be malformed. Let's stop.
            break

    return "\n".join(traceback_lines), idx


def extract_failures_from_log(filepath: str) -> List[Tuple[str, str]]:
    """Scan a log file and extract failure/error blocks.

    Args:
        filepath: Path to the log file.

    Returns:
        A list of tuples: (raw error block, failure type).
    """
    failures: List[Tuple[str, str]] = []
    if not os.path.exists(filepath):
        return failures

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.rstrip() for line in f.readlines()]

    idx = 0
    while idx < len(lines):
        line = lines[idx]

        # 1. Python Traceback
        if "Traceback (most recent call last):" in line:
            tb, next_idx = extract_python_traceback(lines, idx)
            failures.append((tb, "Python Traceback"))
            idx = next_idx
            continue

        # 2. Pytest Failure Block delimiter
        if line.startswith("_____") and line.endswith("_____"):
            # Capture the next few lines representing the test failure details
            pytest_block = [line]
            idx += 1
            while idx < len(lines) and not lines[idx].startswith("====="):
                # Stop if another test starts or we hit traceback
                if "Traceback (most recent call last):" in lines[idx]:
                    break
                pytest_block.append(lines[idx])
                idx += 1
            failures.append(("\n".join(pytest_block), "Pytest Failure"))
            continue

        # 3. Linter/Compiler error match (e.g., "filename.py:12: error: ...")
        # Regex to match file:line: error pattern
        linter_match = re.search(
            r"\b\w+\.py:\d+:(?:\d+:)?\s*(?:error|warning|failed):", line
        )
        if linter_match:
            failures.append((line, "Linter/Compiler Error"))
            idx += 1
            continue

        # 4. Standard ERROR log lines
        if re.search(r"\b(ERROR|FATAL|EXCEPTION)\b", line, re.IGNORECASE):
            # Exclude lines that are part of other checks
            if not any(keyword in line for keyword in ["INFO", "DEBUG"]):
                failures.append((line, "Generic Error Log"))

        idx += 1

    return failures


def group_failures(
    log_files: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Analyze all log files and group failures by root cause.

    Args:
        log_files: List of log file paths to analyze.

    Returns:
        A dictionary mapping sanitized failure templates to details
        containing counts, logs, and representative raw examples.
    """
    groups: Dict[str, Dict[str, Any]] = {}

    for filepath in log_files:
        filename = os.path.basename(filepath)
        raw_failures = extract_failures_from_log(filepath)

        for raw_fail, fail_type in raw_failures:
            sanitized = sanitize_message(raw_fail)

            # Use sanitized template as key
            if sanitized not in groups:
                groups[sanitized] = {
                    "template": sanitized,
                    "type": fail_type,
                    "count": 0,
                    "files": set(),
                    "raw_examples": [],
                }

            groups[sanitized]["count"] += 1
            groups[sanitized]["files"].add(filename)

            # Store up to 3 distinct raw examples for context
            if len(groups[sanitized]["raw_examples"]) < 3:
                if raw_fail not in groups[sanitized]["raw_examples"]:
                    groups[sanitized]["raw_examples"].append(raw_fail)

    return groups


def print_report(groups: Dict[str, Dict[str, Any]], format_type: str = "text") -> None:
    """Print the deduplicated failure report.

    Args:
        groups: The grouped failure dictionary.
        format_type: Output format ('text' or 'markdown').
    """
    sorted_groups = sorted(groups.values(), key=lambda x: x["count"], reverse=True)

    if format_type == "markdown":
        print("# CI Failure Deduplication Report\n")
        print(f"Detected **{len(groups)}** unique root causes across all logs.\n")
        for idx, g in enumerate(sorted_groups, 1):
            print(f"## Root Cause {idx}: {g['type']} (Occurrences: {g['count']})")
            print(f"**Affected Jobs/Files:** {', '.join(sorted(g['files']))}\n")
            print("**Sanitized Template:**")
            print(f"```\n{g['template']}\n```\n")
            print("**Example Raw Trace/Log:**")
            print(f"```\n{g['raw_examples'][0]}\n```\n")
            print("-" * 40 + "\n")
    else:
        print("=" * 80)
        print("                  CI FAILURE DEDUPLICATION REPORT")
        print("=" * 80)
        print(
            f"Found {len(groups)} unique root cause(s) across the analyzed log files.\n"
        )

        for idx, g in enumerate(sorted_groups, 1):
            print(f"[{idx}] Root Cause: {g['type']}")
            print(f"    Occurrences: {g['count']}")
            print(f"    Affected files: {', '.join(sorted(g['files']))}")
            print(f"    Template: {g['template'][:120]}...")
            print("    Representative Example:")
            print("-" * 50)
            # Indent the representative example
            example = g["raw_examples"][0]
            indented = "\n".join("      " + line for line in example.split("\n"))
            print(indented)
            print("-" * 50)
            print()


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="ci-failure-deduper: Group CI failures by root cause."
    )
    parser.add_argument(
        "logs",
        nargs="*",
        help="Log file paths or patterns (e.g. logs/*.log)",
    )
    parser.add_argument(
        "--dir",
        help="Directory containing log files to process",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown"],
        default="text",
        help="Report output format",
    )

    args = parser.parse_args()

    log_files: List[str] = []

    # Resolve positional arguments (files or globs)
    if args.logs:
        for pattern in args.logs:
            matched = glob.glob(pattern)
            if matched:
                log_files.extend(matched)
            elif os.path.exists(pattern):
                log_files.append(pattern)

    # Resolve directory
    if args.dir and os.path.isdir(args.dir):
        for root, _, files in os.walk(args.dir):
            for file in files:
                log_files.append(os.path.join(root, file))

    # Clean duplicates and check exists
    log_files = sorted(list({f for f in log_files if os.path.isfile(f)}))

    if not log_files:
        print(
            "Error: No valid log files found. Please provide logs/directories.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Analyzing {len(log_files)} log files...")
    groups = group_failures(log_files)
    print_report(groups, args.format)


if __name__ == "__main__":
    main()

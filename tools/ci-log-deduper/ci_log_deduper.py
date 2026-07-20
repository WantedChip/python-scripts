#!/usr/bin/env python3
"""CI Log Deduper.

Aggregates multiple failed CI job log files, extracts traceback error patterns,
collapses dynamic addresses/values, and groups them into root failure signatures.
"""

import argparse
import os
import re
from typing import Dict, List


def normalize_error_line(line: str) -> str:
    """Normalize a log/error line by removing numbers, memory addresses, and paths."""
    # Replace timestamps first to avoid numbers match
    line = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<DATE>", line)
    line = re.sub(r"\b\d{2}:\d{2}:\d{2}\b", "<TIME>", line)
    # Replace hex addresses: 0x7f3b8c...
    line = re.sub(r"0x[a-fA-F0-9]+\b", "<HEX>", line)
    # Replace Windows or Unix file paths
    line = re.sub(r"[a-zA-Z]:\\[\\\w\.\-]+", "<PATH>", line)
    line = re.sub(r"\/[\w\.\-\/]+", "<PATH>", line)
    # Replace numbers/digits
    line = re.sub(r"\b\d+\b", "<NUM>", line)
    return line.strip()


def extract_failure_signature(file_path: str) -> str:
    """Scan log file to extract the main traceback or exception error line."""
    if not os.path.exists(file_path):
        return "Unknown failure (file not found)"

    signature_lines = []
    in_traceback = False

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_strip = line.strip()

                # Check Python traceback starts
                if "Traceback (most recent call last)" in line_strip:
                    in_traceback = True
                    signature_lines = [line_strip]
                    continue

                if in_traceback:
                    signature_lines.append(line_strip)
                    # Traceback usually ends with exception name
                    if (
                        len(signature_lines) > 1
                        and not line_strip.startswith("File ")
                        and not line_strip.startswith("at ")
                        and ":" in line_strip
                    ):
                        in_traceback = False
                        return normalize_error_line(line_strip)

                # Check generic error keywords
                if any(
                    k in line_strip.upper()
                    for k in ("ERROR:", "EXCEPTION:", "FAIL:", "FAILED:", "FATAL:")
                ):
                    # Avoid adding generic setup lines
                    if "npm ERR!" in line_strip or "pip" in line_strip.lower():
                        continue
                    signature_lines.append(line_strip)

    except OSError:
        pass

    if signature_lines:
        return normalize_error_line(signature_lines[-1])

    return "Generic unexpected execution failure (no explicit trace found)"


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate multiple failed CI job logs into root failure signatures."
        )
    )
    parser.add_argument(
        "log_files", nargs="+", help="List of CI log files to deduplicate."
    )

    args = parser.parse_args()

    print("========================================================================")
    print("CI LOG DEDUPER: FAILURE SIGNATURES COLLATOR")
    print("========================================================================")
    print(f"Log Files Checked: {len(args.log_files)}")
    print("Analyzing logs and extracting traceback exceptions...")
    print("-" * 80)

    # Map: signature -> list of filenames
    signatures: Dict[str, List[str]] = {}

    for fpath in args.log_files:
        base = os.path.basename(fpath)
        sig = extract_failure_signature(fpath)

        if sig not in signatures:
            signatures[sig] = []
        signatures[sig].append(base)

    # Sort signatures by frequency (descending)
    sorted_sigs = sorted(signatures.items(), key=lambda x: len(x[1]), reverse=True)

    print(f"Discovered {len(sorted_sigs)} distinct root failure signatures:")
    print("=" * 80)

    for idx, (sig, logs) in enumerate(sorted_sigs, 1):
        print(f"{idx}. FAILURE SIGNATURE: {sig}")
        print(f"   Occurrences: {len(logs)} log files")
        print("   Matched Logs:")
        for log_file in logs[:5]:
            print(f"     - {log_file}")
        if len(logs) > 5:
            print(f"     ... and {len(logs) - 5} more files.")
        print("-" * 80)
    print("========================================================================")


if __name__ == "__main__":
    main()

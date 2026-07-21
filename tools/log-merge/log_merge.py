#!/usr/bin/env python3
"""Log Merge.

Takes multiple service log files, extracts timestamps to merge them into a unified
chronological timeline, collapses repeated consecutive errors, and highlights
precursors before failures.
"""

import argparse
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Match ISO 8601 timestamps
ISO_TIMESTAMP_PATTERN = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{3,6})?(?:Z|[+-]\d{2}:?\d{2})?)\b"
)


def parse_timestamp(log_line: str) -> Optional[datetime]:
    """Sniff and parse timestamp from log line, returning datetime object."""
    match = ISO_TIMESTAMP_PATTERN.search(log_line)
    if not match:
        return None

    time_str = match.group(1).replace("T", " ").replace("Z", "")
    if "." in time_str:
        base, frac = time_str.split(".", 1)
        frac_clean = re.split(r"[+\-\s]", frac)[0][:6]
        time_str = f"{base}.{frac_clean}"
    else:
        if " " in time_str:
            date_part, time_part = time_str.split(" ", 1)
            time_part_clean = re.split(r"[+\-]", time_part)[0].strip()
            time_str = f"{date_part} {time_part_clean}"
        else:
            time_str = re.split(r"[+\-]", time_str)[0].strip()

    formats = ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            pass
    return None


def read_log_file(file_path: str) -> List[Dict[str, Any]]:
    """Parse log file entries, associating multi-line logs with preceding timestamps."""
    entries: List[Dict[str, Any]] = []
    base_name = os.path.basename(file_path)
    if not os.path.exists(file_path):
        return entries

    last_dt = datetime.min

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, 1):
                line_strip = line.strip()
                if not line_strip:
                    continue

                dt = parse_timestamp(line_strip)
                if dt:
                    last_dt = dt
                elif last_dt == datetime.min:
                    continue
                else:
                    dt = last_dt

                is_error = False
                if any(
                    err in line_strip.upper()
                    for err in ("ERROR", "CRITICAL", "FATAL", "FAIL", "EXCEPTION")
                ):
                    is_error = True

                entries.append(
                    {
                        "timestamp": dt,
                        "source": base_name,
                        "line_number": line_num,
                        "content": line_strip,
                        "is_error": is_error,
                    }
                )
    except OSError:
        pass
    return entries


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Merge scattered service logs into a unified timeline with "
            "error highlights."
        )
    )
    parser.add_argument(
        "log_files", nargs="+", help="Path list of service log files to merge."
    )
    parser.add_argument("-o", "--output", help="Path to write the merged log timeline.")
    parser.add_argument(
        "-p",
        "--precursors",
        type=int,
        default=3,
        help="Number of timeline lines to display before errors (default: 3).",
    )

    args = parser.parse_args()

    print("========================================================================")
    print("LOG MERGE: UNIFIED TIMELINE BUILDER")
    print("========================================================================")
    print(f"Service Log Files: {', '.join(args.log_files)}")
    print("-" * 80)

    all_entries = []
    for fpath in args.log_files:
        parsed = read_log_file(fpath)
        all_entries.extend(parsed)
        print(f"Parsed {len(parsed):,} entries from: {os.path.basename(fpath)}")

    if not all_entries:
        print("\n[-] No valid log entries with timestamp identifiers discovered.")
        sys.exit(0)

    all_entries.sort(key=lambda x: x["timestamp"])
    print(f"Total merged events: {len(all_entries):,}")
    print("-" * 80)

    collapsed = []
    idx = 0
    while idx < len(all_entries):
        curr = all_entries[idx]
        collapsed.append(curr)
        dup_count = 0

        next_idx = idx + 1
        while next_idx < len(all_entries):
            nxt = all_entries[next_idx]
            curr_text = re.sub(r"\d", "", curr["content"])
            nxt_text = re.sub(r"\d", "", nxt["content"])

            if curr["source"] == nxt["source"] and curr_text == nxt_text:
                dup_count += 1
                next_idx += 1
            else:
                break

        if dup_count > 0:
            collapsed[-1]["content"] += f" [Repeated {dup_count} times]"
            idx = next_idx
        else:
            idx += 1

    output_lines = []
    for line_idx, entry in enumerate(collapsed):
        time_str = entry["timestamp"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        prefix = f"[{time_str}] ({entry['source']}) "

        if entry["is_error"]:
            line_str = f"!!! ERROR: {prefix}{entry['content']}"
            output_lines.append(line_str)

            start = max(0, line_idx - args.precursors)
            if start < line_idx:
                print("\n--- Precursors before failure ---")
                for c_idx in range(start, line_idx):
                    p_entry = collapsed[c_idx]
                    p_time = p_entry["timestamp"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    print(f"  [{p_time}] ({p_entry['source']}) {p_entry['content']}")
                print("-" * 33)
            print(line_str)
        else:
            line_str = f"           {prefix}{entry['content']}"
            output_lines.append(line_str)

    if args.output:
        out_path = os.path.abspath(args.output)
        try:
            with open(out_path, "w", encoding="utf-8") as out_f:
                out_f.write("\n".join(output_lines) + "\n")
            print(f"\n[+] Unified timeline successfully written to: {out_path}")
        except OSError as e:
            print(f"[-] Error writing output timeline file: {e}", file=sys.stderr)
    print("========================================================================")


if __name__ == "__main__":
    main()

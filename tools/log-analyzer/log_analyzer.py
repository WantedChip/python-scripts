"""Log Analyzer.

Parses large log files, groups repeated errors, detects frequency spikes,
and summarizes the most important failures.
"""

import argparse
import collections
import datetime
import json
import logging
import math
import os
import re
import sys
from typing import Any, Dict, Generator, List, Optional, Tuple

# Predefined regex patterns for common log formats.
# Returns tuple of:
# (regex_pattern, timestamp_group_index, level_group_index,
#  message_group_index, timestamp_format)
LOG_FORMATS = {
    "combined": (
        r"^(\S+) \S+ \S+ \[([^\]]+)\] \"(\S+)\s?([^\"]*)\s?(\S+)\" "
        r"(\d{3}) (\S+)(?: \"([^\"\\]*(?:\\.[^\"\\]*)*)\" "
        r"\"([^\"\\]*(?:\\.[^\"\\]*)*)\")?$",
        2,
        0,
        4,
        "%d/%b/%Y:%H:%M:%S %z",
    ),
    "common": (
        r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\S+)\s?([^\"]*)\s?(\S+)" (\d{3}) (\S+)$',
        2,  # Timestamp group
        0,  # No explicit log level, we'll infer it from HTTP status code
        4,  # Use request path or full request as message representation
        "%d/%b/%Y:%H:%M:%S %z",
    ),
    "python": (
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\S+) - (\S+) - (.*)$",
        1,
        2,
        4,
        "%Y-%m-%d %H:%M:%S,%f",
    ),
    "log4j": (
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[([^\]]+)\] (\S+)\s+(\S+) - (.*)$",
        1,
        3,
        5,
        "%Y-%m-%d %H:%M:%S",
    ),
}

# Regex patterns for normalization of log messages
NORM_HEX = re.compile(r"0x[0-9a-fA-F]+")
NORM_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
NORM_IP = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
NORM_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
NORM_QUOTES = re.compile(r'"[^"]*"|\'[^\']*\'')


def parse_timestamp(ts_str: str, ts_format: str) -> Optional[datetime.datetime]:
    """Parse a timestamp string into a datetime object.

    Args:
        ts_str: The timestamp string.
        ts_format: The format of the timestamp.

    Returns:
        The datetime object if successful, else None.
    """
    try:
        return datetime.datetime.strptime(ts_str, ts_format)
    except ValueError:
        try:
            # Fallback for common logs timezone offset
            if " " in ts_str:
                parts = ts_str.split()
                if len(parts) > 1:
                    return datetime.datetime.strptime(parts[0], ts_format.split()[0])
            return None
        except ValueError:
            return None


def normalize_message(msg: str) -> str:
    """Normalize a log message by replacing dynamic parts with placeholders.

    Args:
        msg: The log message.

    Returns:
        The normalized message.
    """
    msg = NORM_HEX.sub("<HEX>", msg)
    msg = NORM_UUID.sub("<UUID>", msg)
    msg = NORM_IP.sub("<IP>", msg)
    msg = NORM_QUOTES.sub("<STR>", msg)
    msg = NORM_NUM.sub("<NUM>", msg)
    msg = re.sub(r"\s+", " ", msg).strip()
    return msg


def auto_detect_format(
    sample_lines: List[str],
) -> Tuple[Optional[str], Optional[re.Pattern]]:
    """Auto-detects the log format based on a few sample lines.

    Args:
        sample_lines: List of sample lines from the log.

    Returns:
        A tuple of (format_name, compiled_pattern) or (None, None).
    """
    for fmt_name, (pattern_str, _, _, _, _) in LOG_FORMATS.items():
        pattern = re.compile(pattern_str)
        matched_count = sum(1 for line in sample_lines if pattern.match(line))
        if matched_count >= len(sample_lines) * 0.5 and matched_count > 0:
            return fmt_name, pattern
    return None, None


def read_log_file(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
    file_path: str,
    pattern: Optional[re.Pattern],
    ts_idx: int,
    level_idx: int,
    msg_idx: int,
    ts_format: Optional[str],
) -> Generator[Dict[str, Any], None, None]:
    """Generator reading log file line by line and yielding parsed entries.

    Args:
        file_path: Path to the log file.
        pattern: Compiled regex pattern.
        ts_idx: 1-based index of timestamp group in match.
        level_idx: 1-based index of level group in match.
        msg_idx: 1-based index of message group in match.
        ts_format: Optional strftime format for the timestamp.

    Yields:
        Dictionaries containing 'timestamp', 'level', 'message', 'raw', 'line_num'.
    """
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line:
                continue

            if not pattern:
                yield {
                    "timestamp": None,
                    "level": "UNKNOWN",
                    "message": line,
                    "raw": line,
                    "line_num": line_num,
                }
                continue

            match = pattern.match(line)
            if not match:
                yield {
                    "timestamp": None,
                    "level": "UNKNOWN",
                    "message": line,
                    "raw": line,
                    "line_num": line_num,
                }
                continue

            groups = match.groups()
            ts_str = groups[ts_idx - 1] if 0 < ts_idx <= len(groups) else None
            level_str = (
                groups[level_idx - 1].upper()
                if 0 < level_idx <= len(groups)
                else "UNKNOWN"
            )
            msg_str = groups[msg_idx - 1] if 0 < msg_idx <= len(groups) else line

            if level_idx == 0 and len(groups) >= 6:
                status_code = groups[5]
                if status_code.startswith(("4", "5")):
                    level_str = "ERROR" if status_code.startswith("5") else "WARNING"
                else:
                    level_str = "INFO"

            dt = None
            if ts_str and ts_format:
                dt = parse_timestamp(ts_str, ts_format)

            yield {
                "timestamp": dt,
                "level": level_str,
                "message": msg_str,
                "raw": line,
                "line_num": line_num,
            }


def analyze_spikes(
    timestamps: List[datetime.datetime], window_minutes: int, threshold_stddev: float
) -> List[Tuple[datetime.datetime, datetime.datetime, int, float]]:
    """Analyzes list of timestamps to find windows with a spike in volume.

    Args:
        timestamps: List of datetime objects, sorted chronologically.
        window_minutes: The window size in minutes.
        threshold_stddev: Spike threshold in terms of standard deviation.

    Returns:
        List of tuples: (window_start, window_end, count, stddevs_above_mean)
    """
    if not timestamps:
        return []

    delta = datetime.timedelta(minutes=window_minutes)
    start_time = timestamps[0]
    start_time = start_time.replace(
        minute=(start_time.minute // window_minutes) * window_minutes,
        second=0,
        microsecond=0,
    )

    buckets: Dict[datetime.datetime, int] = collections.defaultdict(int)
    for ts in timestamps:
        bucket_start = start_time + (
            math.floor((ts - start_time) / delta) * delta
        )
        buckets[bucket_start] += 1

    counts = list(buckets.values())
    if not counts:
        return []

    mean = sum(counts) / len(counts)
    variance = sum((x - mean) ** 2 for x in counts) / len(counts)
    stddev = math.sqrt(variance)

    spikes = []
    if stddev == 0:
        return []

    for bucket_start, count in sorted(buckets.items()):
        stddevs_above = (count - mean) / stddev
        if stddevs_above >= threshold_stddev and count > mean:
            spikes.append(
                (bucket_start, bucket_start + delta, count, stddevs_above)
            )

    return spikes


def analyze_log(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements,too-many-positional-arguments
    file_path: str,
    fmt_type: Optional[str] = None,
    custom_pattern: Optional[str] = None,
    ts_group: int = 1,
    level_group: int = 2,
    msg_group: int = 3,
    ts_format: Optional[str] = None,
    window_minutes: int = 5,
    spike_threshold: float = 2.0,
) -> Dict[str, Any]:
    """Performs the complete log analysis.

    Args:
        file_path: Path to the log file.
        fmt_type: Format name (common, combined, python, log4j).
        custom_pattern: Custom regex pattern.
        ts_group: 1-based index of timestamp group in custom pattern.
        level_group: 1-based index of level group in custom pattern.
        msg_group: 1-based index of message group in custom pattern.
        ts_format: Format string for the timestamp parsing.
        window_minutes: Spike detection window in minutes.
        spike_threshold: Spike threshold standard deviation.

    Returns:
        Analysis summary dict.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Log file not found: {file_path}")

    pattern = None
    selected_ts_format = ts_format

    if custom_pattern:
        pattern = re.compile(custom_pattern)
        ts_idx, level_idx, msg_idx = ts_group, level_group, msg_group
    elif fmt_type and fmt_type in LOG_FORMATS:
        pattern_str, ts_idx, level_idx, msg_idx, default_ts_format = LOG_FORMATS[
            fmt_type
        ]
        pattern = re.compile(pattern_str)
        if not selected_ts_format:
            selected_ts_format = default_ts_format
    else:
        sample_lines = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(20):
                line = f.readline()
                if not line:
                    break
                sample_lines.append(line.rstrip("\r\n"))

        fmt_name, pattern = auto_detect_format(sample_lines)
        if fmt_name:
            logging.info("Auto-detected log format: %s", fmt_name)
            _, ts_idx, level_idx, msg_idx, default_ts_format = LOG_FORMATS[
                fmt_name
            ]
            if not selected_ts_format:
                selected_ts_format = default_ts_format
        else:
            logging.warning("Could not auto-detect format. Parsing as raw lines.")
            ts_idx, level_idx, msg_idx = 0, 0, 0

    total_lines = 0
    parsed_lines = 0
    errors_count = 0
    warnings_count = 0

    error_groups: Dict[str, Dict[str, Any]] = {}
    timestamps: List[datetime.datetime] = []

    for entry in read_log_file(
        file_path, pattern, ts_idx, level_idx, msg_idx, selected_ts_format
    ):
        total_lines += 1
        if entry["timestamp"] or pattern:
            parsed_lines += 1

        level = entry["level"]
        if level in ("ERROR", "CRITICAL", "FATAL"):
            errors_count += 1
            is_error = True
        elif level in ("WARNING", "WARN"):
            warnings_count += 1
            is_error = False
        else:
            is_error = False

        if entry["timestamp"]:
            timestamps.append(entry["timestamp"])

        if is_error:
            norm_msg = normalize_message(entry["message"])
            if norm_msg not in error_groups:
                error_groups[norm_msg] = {
                    "count": 0,
                    "sample": entry["message"],
                    "first_seen": entry["timestamp"],
                    "last_seen": entry["timestamp"],
                    "lines": [],
                }
            error_groups[norm_msg]["count"] += 1
            if entry["timestamp"]:
                if (
                    not error_groups[norm_msg]["first_seen"]
                    or entry["timestamp"]
                    < error_groups[norm_msg]["first_seen"]
                ):
                    error_groups[norm_msg]["first_seen"] = entry["timestamp"]
                if (
                    not error_groups[norm_msg]["last_seen"]
                    or entry["timestamp"] > error_groups[norm_msg]["last_seen"]
                ):
                    error_groups[norm_msg]["last_seen"] = entry["timestamp"]
            error_groups[norm_msg]["lines"].append(entry["line_num"])

    timestamps.sort()
    spikes = analyze_spikes(timestamps, window_minutes, spike_threshold)

    sorted_errors = sorted(
        [
            {
                "normalized": k,
                "count": v["count"],
                "sample": v["sample"],
                "first_seen": (
                    v["first_seen"].isoformat() if v["first_seen"] else None
                ),
                "last_seen": (
                    v["last_seen"].isoformat() if v["last_seen"] else None
                ),
                "lines": v["lines"][:10],
            }
            for k, v in error_groups.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "summary": {
            "file_path": file_path,
            "total_lines": total_lines,
            "parsed_lines": parsed_lines,
            "errors": errors_count,
            "warnings": warnings_count,
        },
        "errors": sorted_errors,
        "spikes": [
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "count": count,
                "stddevs_above": stddevs,
            }
            for start, end, count, stddevs in spikes
        ],
    }


def print_report(results: Dict[str, Any]) -> None:
    """Prints a user-friendly report to stdout.

    Args:
        results: Dict containing analysis results.
    """
    summary = results["summary"]
    print("=" * 60)
    print("LOG ANALYSIS REPORT")
    print("=" * 60)
    print(f"File:        {summary['file_path']}")
    print(f"Total Lines: {summary['total_lines']:,}")
    print(f"Parsed:      {summary['parsed_lines']:,}")
    print(f"Errors:      {summary['errors']:,}")
    print(f"Warnings:    {summary['warnings']:,}")
    print("=" * 60)

    print("\nTOP ERROR GROUPS:")
    if not results["errors"]:
        print("  No errors found.")
    else:
        for idx, err in enumerate(results["errors"][:5], 1):
            print(f"\n{idx}. Count: {err['count']}")
            print(f"   Sample:     {err['sample']}")
            print(f"   Normalized: {err['normalized']}")
            if err["first_seen"]:
                print(f"   Time Range: {err['first_seen']} to {err['last_seen']}")
            print(f"   Lines:      {', '.join(map(str, err['lines']))}")

    print("\n" + "=" * 60)
    print("DETECTED SPIKES:")
    if not results["spikes"]:
        print("  No volume spikes detected.")
    else:
        for spike in results["spikes"][:5]:
            print(
                f"  Window: {spike['start']} to {spike['end']} | "
                f"Count: {spike['count']} "
                f"({spike['stddevs_above']:.2f} std devs above mean)"
            )
    print("=" * 60)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Parse huge log files, group errors, detect spikes, and "
            "summarize failures."
        )
    )
    parser.add_argument("file", help="Path to the log file")
    parser.add_argument(
        "-t",
        "--type",
        choices=list(LOG_FORMATS.keys()),
        help="Predefined log format type (auto-detected if omitted)",
    )
    parser.add_argument(
        "-p", "--pattern", help="Custom regex pattern for matching lines"
    )
    parser.add_argument(
        "--ts-group",
        type=int,
        default=1,
        help="Group index of timestamp in custom regex pattern",
    )
    parser.add_argument(
        "--level-group",
        type=int,
        default=2,
        help="Group index of log level in custom regex pattern",
    )
    parser.add_argument(
        "--msg-group",
        type=int,
        default=3,
        help="Group index of message in custom regex pattern",
    )
    parser.add_argument(
        "--ts-format",
        help="Timestamp format (e.g. '%%Y-%%m-%%d %%H:%%M:%%S')",
    )
    parser.add_argument(
        "-w",
        "--window",
        type=int,
        default=5,
        help="Window size in minutes for spike detection (default: 5)",
    )
    parser.add_argument(
        "-s",
        "--spike-threshold",
        type=float,
        default=2.0,
        help="Spike detection threshold in std devs (default: 2.0)",
    )
    parser.add_argument(
        "-j", "--json-output", action="store_true", help="Output results in JSON format"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    try:
        results = analyze_log(
            file_path=args.file,
            fmt_type=args.type,
            custom_pattern=args.pattern,
            ts_group=args.ts_group,
            level_group=args.level_group,
            msg_group=args.msg_group,
            ts_format=args.ts_format,
            window_minutes=args.window,
            spike_threshold=args.spike_threshold,
        )

        if args.json_output:
            print(json.dumps(results, indent=2))
        else:
            print_report(results)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-except
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

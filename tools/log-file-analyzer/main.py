"""Log File Analyzer.

Parses web server logs (Nginx, Apache, Combined Log Format) and reports top IP
addresses, status codes, top requested paths, and bandwidth.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import csv
import json
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

# Combined/Common Log Format Regex Pattern
LOG_PATTERN = re.compile(
    r"^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+"
    r'"(?P<request>[^"]*)"\s+(?P<status>\d{3})\s+(?P<bytes>\d+|-)'
    r'(?:\s+"(?P<referrer>[^"]*)"\s+"(?P<user_agent>[^"]*)")?'
)


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single log line into a dictionary.

    Args:
        line: Raw log line string.

    Returns:
        Dictionary with ip, timestamp, method, path, status, bytes, or None.
    """
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None

    data = match.groupdict()
    ip = data["ip"]
    raw_time = data["time"]
    raw_request = data["request"]
    status = int(data["status"])
    bytes_str = data["bytes"]
    num_bytes = int(bytes_str) if bytes_str.isdigit() else 0

    # Extract HTTP method and path from request string
    request_parts = raw_request.split()
    method = request_parts[0] if len(request_parts) > 0 else "UNKNOWN"
    path = request_parts[1] if len(request_parts) > 1 else "/"

    return {
        "ip": ip,
        "timestamp": raw_time,
        "method": method,
        "path": path,
        "status": status,
        "bytes": num_bytes,
        "referrer": data.get("referrer"),
        "user_agent": data.get("user_agent"),
    }


def analyze_log_file(filepath: str) -> Dict[str, Any]:
    """Parse and aggregate metrics from a web server log file.

    Args:
        filepath: Path to the log file.

    Returns:
        Aggregated summary dictionary.
    """
    total_requests = 0
    total_bytes = 0
    unparsed_lines = 0

    ip_counter: Counter[str] = Counter()
    status_counter: Counter[int] = Counter()
    path_counter: Counter[str] = Counter()

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            entry = parse_log_line(line)
            if not entry:
                unparsed_lines += 1
                continue

            total_requests += 1
            total_bytes += entry["bytes"]
            ip_counter[entry["ip"]] += 1
            status_counter[entry["status"]] += 1
            path_counter[entry["path"]] += 1

    bandwidth_mb = round(total_bytes / (1024 * 1024), 2)
    avg_bandwidth_kb = (
        round((total_bytes / total_requests) / 1024, 2) if total_requests > 0 else 0.0
    )

    return {
        "file": filepath,
        "total_requests": total_requests,
        "unparsed_lines": unparsed_lines,
        "total_bandwidth_bytes": total_bytes,
        "total_bandwidth_mb": bandwidth_mb,
        "avg_bandwidth_kb_per_req": avg_bandwidth_kb,
        "top_ips": dict(ip_counter.most_common(10)),
        "status_codes": dict(status_counter.most_common()),
        "top_paths": dict(path_counter.most_common(10)),
    }


def print_dashboard_summary(summary: Dict[str, Any]) -> None:
    """Print terminal dashboard summary of log file metrics.

    Args:
        summary: Aggregated summary dictionary.
    """
    print("\n" + "=" * 65)
    print("               WEB SERVER LOG ANALYSIS DASHBOARD")
    print("=" * 65)
    print(f" File Analyzed     : {summary['file']}")
    print(f" Total Requests    : {summary['total_requests']}")
    mb = summary["total_bandwidth_mb"]
    tb = summary["total_bandwidth_bytes"]
    print(f" Total Bandwidth   : {mb} MB ({tb} Bytes)")
    print(f" Avg Request Size  : {summary['avg_bandwidth_kb_per_req']} KB")
    if summary["unparsed_lines"] > 0:
        print(f" Unparsed Lines    : {summary['unparsed_lines']}")
    print("-" * 65)

    print("\n--- STATUS CODES ---")
    tot = summary["total_requests"]
    for code, count in summary["status_codes"].items():
        pct = (count / tot) * 100 if tot > 0 else 0
        print(f" HTTP {code} : {count:<8} ({pct:.1f}%)")

    print("\n--- TOP 10 IP ADDRESSES ---")
    print(f" {'IP ADDRESS':<25} | {'REQUESTS':<10}")
    print("-" * 40)
    for ip, count in summary["top_ips"].items():
        print(f" {ip:<25} | {count:<10}")

    print("\n--- TOP 10 REQUESTED PATHS ---")
    print(f" {'PATH':<40} | {'HITS':<10}")
    print("-" * 55)
    for path, count in summary["top_paths"].items():
        truncated_path = path[:38] + ".." if len(path) > 40 else path
        print(f" {truncated_path:<40} | {count:<10}")
    print("=" * 65 + "\n")


def export_json(summary: Dict[str, Any], filepath: str) -> None:
    """Export summary analysis to JSON file.

    Args:
        summary: Summary dict.
        filepath: JSON file path.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


def export_csv(summary: Dict[str, Any], filepath: str) -> None:
    """Export top metrics to a multi-section CSV file.

    Args:
        summary: Summary dict.
        filepath: CSV file path.
    """
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Section", "Key", "Value"])
        tot_req = summary["total_requests"]
        tot_mb = summary["total_bandwidth_mb"]
        writer.writerow(["Overview", "Total Requests", tot_req])
        writer.writerow(["Overview", "Total Bandwidth MB", tot_mb])

        for code, count in summary["status_codes"].items():
            writer.writerow(["StatusCode", f"HTTP {code}", count])

        for ip, count in summary["top_ips"].items():
            writer.writerow(["TopIP", ip, count])

        for path, count in summary["top_paths"].items():
            writer.writerow(["TopPath", path, count])


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Parse Nginx/Apache log files and analyze web traffic."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("logfile", type=str, help="Path to Nginx/Apache log file")
    parser.add_argument(
        "-j", "--json", type=str, help="Path to export report to JSON file"
    )
    parser.add_argument(
        "-c", "--csv", type=str, help="Path to export report to CSV file"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Log File Analyzer."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    try:
        summary = analyze_log_file(parsed.logfile)
    except FileNotFoundError:
        print(f"Error: Log file '{parsed.logfile}' not found.", file=sys.stderr)
        return 1

    print_dashboard_summary(summary)

    if parsed.json:
        export_json(summary, parsed.json)
        print(f"Exported JSON report to '{parsed.json}'.")
    if parsed.csv:
        export_csv(summary, parsed.csv)
        print(f"Exported CSV report to '{parsed.csv}'.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

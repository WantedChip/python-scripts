"""Time Sync Auditor CLI Tool.

Audits NTP and chrony synchronization health across multi-host Linux environments
or parses time sync CLI logs (chrony, ntpstat, ntpq) and JSON aggregated status reports.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-instance-attributes,too-many-arguments
# pylint: disable=too-many-positional-arguments

import argparse
import csv
import io
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, List, Optional


@dataclass
class HostTimeStatus:
    """Dataclass holding time synchronization state for a single host."""

    host: str
    service: str  # chrony, ntpstat, ntpq, unknown
    synced: bool
    reference_source: Optional[str] = None
    stratum: Optional[int] = None
    offset_ms: Optional[float] = None
    frequency_ppm: Optional[float] = None
    root_delay_ms: Optional[float] = None
    status: str = "UNKNOWN"  # HEALTHY, WARNING, CRITICAL, UNKNOWN
    health_issues: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.health_issues is None:
            self.health_issues = []


def parse_chrony_tracking(text: str, host: str = "localhost") -> HostTimeStatus:
    """Parse `chronyc tracking` text output into HostTimeStatus.

    Args:
        text: Raw stdout of chronyc tracking.
        host: Host identifier string.

    Returns:
        HostTimeStatus dataclass instance.
    """
    ref_match = re.search(r"Reference ID\s*:\s*([^\n]+)", text)
    stratum_match = re.search(r"Stratum\s*:\s*(\d+)", text)
    offset_match = re.search(
        r"System time\s*:\s*([+-]?\d+\.?\d*(?:e[+-]?\d+)?)\s*seconds\s*(slow|fast)?",
        text,
        re.IGNORECASE,
    )
    freq_match = re.search(
        r"Frequency\s*:\s*([+-]?\d+\.?\d*)\s*ppm", text, re.IGNORECASE
    )
    delay_match = re.search(
        r"Root delay\s*:\s*([+-]?\d+\.?\d*(?:e[+-]?\d+)?)\s*seconds",
        text,
        re.IGNORECASE,
    )

    ref_source = ref_match.group(1).strip() if ref_match else None
    stratum = int(stratum_match.group(1)) if stratum_match else None

    offset_ms = None
    if offset_match:
        val_sec = float(offset_match.group(1))
        direction = (offset_match.group(2) or "").lower()
        if direction == "slow":
            val_sec = -abs(val_sec)
        offset_ms = round(val_sec * 1000.0, 4)

    freq_ppm = float(freq_match.group(1)) if freq_match else None
    delay_ms = round(float(delay_match.group(1)) * 1000.0, 4) if delay_match else None

    # Check unsynchronized reference ID (e.g. 00000000)
    synced = True
    if (
        not ref_source
        or "00000000" in ref_source
        or "unconfigured" in ref_source.lower()
    ):
        synced = False

    return HostTimeStatus(
        host=host,
        service="chrony",
        synced=synced,
        reference_source=ref_source,
        stratum=stratum,
        offset_ms=offset_ms,
        frequency_ppm=freq_ppm,
        root_delay_ms=delay_ms,
    )


def parse_ntpstat(text: str, host: str = "localhost") -> HostTimeStatus:
    """Parse `ntpstat` text output into HostTimeStatus.

    Args:
        text: Raw stdout of ntpstat command.
        host: Host identifier string.

    Returns:
        HostTimeStatus dataclass instance.
    """
    if "unsynchronised" in text.lower() or "not synchronised" in text.lower():
        return HostTimeStatus(
            host=host,
            service="ntpstat",
            synced=False,
            status="CRITICAL",
            health_issues=["Host NTP is unsynchronised"],
        )

    ref_match = re.search(
        r"synchronised to NTP server \(([^)]+)\) at stratum (\d+)", text
    )
    offset_match = re.search(r"time correct to within (\d+)\s*ms", text)

    ref_source = ref_match.group(1) if ref_match else None
    stratum = int(ref_match.group(2)) if ref_match else None
    offset_ms = float(offset_match.group(1)) if offset_match else None

    return HostTimeStatus(
        host=host,
        service="ntpstat",
        synced=True,
        reference_source=ref_source,
        stratum=stratum,
        offset_ms=offset_ms,
    )


def parse_ntpq(text: str, host: str = "localhost") -> HostTimeStatus:
    """Parse `ntpq -p` peers table text output.

    Args:
        text: Raw stdout of ntpq -p.
        host: Host identifier string.

    Returns:
        HostTimeStatus dataclass instance.
    """
    active_peer_line = None
    for line in text.splitlines():
        if line.startswith("*"):
            active_peer_line = line
            break

    if not active_peer_line:
        msg = "No active peer synchronization ('*' source missing in ntpq)"
        return HostTimeStatus(
            host=host,
            service="ntpq",
            synced=False,
            status="CRITICAL",
            health_issues=[msg],
        )

    tokens = active_peer_line[1:].split()
    ref_source = tokens[0] if tokens else "unknown"
    stratum = int(tokens[2]) if len(tokens) > 2 and tokens[2].isdigit() else None
    offset_ms = float(tokens[8]) if len(tokens) > 8 else None
    jitter_ms = float(tokens[9]) if len(tokens) > 9 else None

    return HostTimeStatus(
        host=host,
        service="ntpq",
        synced=True,
        reference_source=ref_source,
        stratum=stratum,
        offset_ms=offset_ms,
        root_delay_ms=jitter_ms,
    )


def detect_and_parse_log(text: str, host: str = "localhost") -> HostTimeStatus:
    """Auto-detect format of time sync log and parse into HostTimeStatus.

    Args:
        text: Input string output.
        host: Host label.

    Returns:
        HostTimeStatus dataclass instance.
    """
    if "Reference ID" in text or "System time" in text:
        return parse_chrony_tracking(text, host=host)
    if (
        "ntpstat" in text.lower()
        or "synchronised to ntp" in text.lower()
        or "unsynchronised" in text.lower()
    ):
        return parse_ntpstat(text, host=host)
    if ("remote" in text and "refid" in text) or text.strip().startswith("*"):
        return parse_ntpq(text, host=host)

    # Fallback default
    return HostTimeStatus(
        host=host,
        service="unknown",
        synced=False,
        status="UNKNOWN",
        health_issues=["Unrecognized time synchronization log format"],
    )


def evaluate_health(
    item: HostTimeStatus,
    max_offset_warn_ms: float = 10.0,
    max_offset_crit_ms: float = 100.0,
    max_stratum_warn: int = 4,
    max_stratum_crit: int = 10,
    max_drift_ppm: float = 100.0,
) -> None:
    """Evaluate health status of a host based on drift and stratum thresholds.

    Args:
        item: Target HostTimeStatus object (mutated in place).
        max_offset_warn_ms: Offset warning threshold in ms.
        max_offset_crit_ms: Offset critical threshold in ms.
        max_stratum_warn: Stratum warning threshold.
        max_stratum_crit: Stratum critical threshold.
        max_drift_ppm: Frequency drift warning threshold in ppm.
    """
    issues = item.health_issues if item.health_issues is not None else []

    if not item.synced:
        item.status = "CRITICAL"
        if "Host time is unsynchronized" not in issues:
            issues.append("Host time is unsynchronized")
        item.health_issues = issues
        return

    severity = "HEALTHY"

    if item.offset_ms is not None:
        abs_offset = abs(item.offset_ms)
        if abs_offset >= max_offset_crit_ms:
            severity = "CRITICAL"
            msg = (
                f"Critical offset drift ({item.offset_ms} ms >= "
                f"{max_offset_crit_ms} ms)"
            )
            issues.append(msg)
        elif abs_offset >= max_offset_warn_ms:
            if severity != "CRITICAL":
                severity = "WARNING"
            msg = (
                f"Elevated offset drift ({item.offset_ms} ms >= "
                f"{max_offset_warn_ms} ms)"
            )
            issues.append(msg)

    if item.stratum is not None:
        if item.stratum >= max_stratum_crit:
            severity = "CRITICAL"
            msg = f"Critical stratum height ({item.stratum} >= " f"{max_stratum_crit})"
            issues.append(msg)
        elif item.stratum >= max_stratum_warn:
            if severity != "CRITICAL":
                severity = "WARNING"
            msg = f"High stratum height ({item.stratum} >= " f"{max_stratum_warn})"
            issues.append(msg)

    if item.frequency_ppm is not None:
        if abs(item.frequency_ppm) >= max_drift_ppm:
            if severity != "CRITICAL":
                severity = "WARNING"
            msg = (
                f"Excessive frequency drift ({item.frequency_ppm} ppm >= "
                f"{max_drift_ppm} ppm)"
            )
            issues.append(msg)

    item.status = severity
    item.health_issues = issues


def parse_json_input(json_data: Any) -> List[HostTimeStatus]:
    """Parse JSON dataset containing multi-host time sync logs or status objects.

    Args:
        json_data: Loaded JSON structure (list or dict).

    Returns:
        List of HostTimeStatus items.
    """
    results: List[HostTimeStatus] = []

    if isinstance(json_data, dict):
        for host_name, content in json_data.items():
            if isinstance(content, str):
                results.append(detect_and_parse_log(content, host=host_name))
            elif isinstance(content, dict):
                raw_out = content.get("output") or content.get("raw") or ""
                st = detect_and_parse_log(raw_out, host=host_name)
                if "service" in content:
                    st.service = content["service"]
                results.append(st)
    elif isinstance(json_data, list):
        for idx, entry in enumerate(json_data):
            if isinstance(entry, dict):
                h_name = entry.get("host") or entry.get("hostname") or f"host_{idx+1}"
                raw_out = entry.get("output") or entry.get("raw") or ""
                results.append(detect_and_parse_log(raw_out, host=h_name))

    return results


def format_table_report(hosts: List[HostTimeStatus]) -> str:
    """Format host status list into terminal summary table.

    Args:
        hosts: List of HostTimeStatus items.

    Returns:
        Formatted summary report string.
    """
    bdr = "=" * 88
    sub_bdr = "-" * 88
    lines = [
        bdr,
        " TIME SYNCHRONIZATION AUDIT REPORT",
        bdr,
        f" Total Hosts Audited: {len(hosts)}",
        f" Healthy: {sum(1 for h in hosts if h.status == 'HEALTHY')} | "
        f" Warnings: {sum(1 for h in hosts if h.status == 'WARNING')} | "
        f" Critical: {sum(1 for h in hosts if h.status == 'CRITICAL')}",
        sub_bdr,
        (
            f"{'HOST':<20} | {'SERVICE':<8} | {'SYNCED':<6} | "
            f"{'STRATUM':<7} | {'OFFSET (ms)':<12} | {'STATUS':<9}"
        ),
        sub_bdr,
    ]

    for h in hosts:
        synced_str = "YES" if h.synced else "NO"
        offset_str = f"{h.offset_ms:+.3f}" if h.offset_ms is not None else "N/A"
        stratum_str = str(h.stratum) if h.stratum is not None else "N/A"

        row_s = (
            f"{h.host:<20} | {h.service:<8} | {synced_str:<6} | "
            f"{stratum_str:<7} | {offset_str:<12} | {h.status:<9}"
        )
        lines.append(row_s)
        if h.health_issues:
            for issue in h.health_issues:
                lines.append(f"  └── Issue: {issue}")

    lines.append(bdr)
    return "\n".join(lines)


def format_csv_report(hosts: List[HostTimeStatus]) -> str:
    """Export host status list as CSV formatted string.

    Args:
        hosts: List of HostTimeStatus items.

    Returns:
        CSV string content.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "host",
            "service",
            "synced",
            "status",
            "reference_source",
            "stratum",
            "offset_ms",
            "frequency_ppm",
            "root_delay_ms",
            "health_issues",
        ]
    )

    for h in hosts:
        writer.writerow(
            [
                h.host,
                h.service,
                h.synced,
                h.status,
                h.reference_source or "",
                h.stratum if h.stratum is not None else "",
                h.offset_ms if h.offset_ms is not None else "",
                h.frequency_ppm if h.frequency_ppm is not None else "",
                h.root_delay_ms if h.root_delay_ms is not None else "",
                "; ".join(h.health_issues or []),
            ]
        )

    return output.getvalue()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = "Audit NTP/chrony time synchronization health across Linux hosts."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("-f", "--file", help="Path to single log file to audit.")
    parser.add_argument(
        "-j", "--json-input", help="Path to multi-host JSON dataset file."
    )
    parser.add_argument(
        "-H",
        "--host",
        default="localhost",
        help="Host label for single file input.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to write report output (defaults to stdout).",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output report format.",
    )
    parser.add_argument(
        "--max-offset-warn",
        type=float,
        default=10.0,
        help="Offset warning threshold in ms (default: 10.0).",
    )
    parser.add_argument(
        "--max-offset-crit",
        type=float,
        default=100.0,
        help="Offset critical threshold in ms (default: 100.0).",
    )
    parser.add_argument(
        "--max-stratum-warn",
        type=int,
        default=4,
        help="Stratum warning threshold (default: 4).",
    )
    parser.add_argument(
        "--max-drift-ppm",
        type=float,
        default=100.0,
        help="Frequency drift warning threshold in ppm (default: 100.0).",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point for time-sync-auditor."""
    args = parse_args(argv)

    if not args.file and not args.json_input:
        msg = "Error: Either --file or --json-input must be provided."
        print(msg, file=sys.stderr)
        return 1

    hosts: List[HostTimeStatus] = []

    if args.file:
        file_path = Path(args.file)
        if not file_path.is_file():
            print(f"Error: Input file not found: {args.file}", file=sys.stderr)
            return 1
        raw_text = file_path.read_text(encoding="utf-8", errors="replace")
        hosts.append(detect_and_parse_log(raw_text, host=args.host))

    if args.json_input:
        json_path = Path(args.json_input)
        if not json_path.is_file():
            err_msg = f"Error: JSON input file not found: {args.json_input}"
            print(err_msg, file=sys.stderr)
            return 1
        try:
            json_data = json.loads(json_path.read_text(encoding="utf-8"))
            hosts.extend(parse_json_input(json_data))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Error parsing JSON input: {exc}", file=sys.stderr)
            return 1

    # Evaluate health thresholds for all hosts
    for h in hosts:
        evaluate_health(
            h,
            max_offset_warn_ms=args.max_offset_warn,
            max_offset_crit_ms=args.max_offset_crit,
            max_stratum_warn=args.max_stratum_warn,
            max_drift_ppm=args.max_drift_ppm,
        )

    if args.format == "json":
        output_content = json.dumps([asdict(h) for h in hosts], indent=2)
    elif args.format == "csv":
        output_content = format_csv_report(hosts)
    else:
        output_content = format_table_report(hosts)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_content, encoding="utf-8")
        print(f"Time sync audit report written to: {args.output}")
    else:
        print(output_content)

    has_critical = any(h.status == "CRITICAL" for h in hosts)
    return 2 if has_critical else 0


if __name__ == "__main__":
    sys.exit(main())

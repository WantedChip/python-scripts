#!/usr/bin/env python3
"""Service Timeline Utility.

Merges application logs, container events, deployments, and system logs into
a unified chronological timeline for incident investigation.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

SEVERITY_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "NOTICE": 25,
    "WARN": 30,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
    "FATAL": 50,
    "RESTART": 45,
    "DEPLOY": 45,
}

ISO_PAT = (
    r"\b(\d{4}-\d{2}-\d{2}[T"
    + r" ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\b"
)
SEV_PAT = (
    r"\b(DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL|RESTART|DEPLOY(?:MENT)?)\b"
)


@dataclass
class Event:
    """Class representing a parsed log event."""

    timestamp: datetime
    raw_timestamp: str
    source: str
    severity: str
    message: str


class EventParser:
    """Parses timestamps and extracts structured events from log files."""

    # Timestamp patterns
    ISO_REGEX = re.compile(ISO_PAT)
    SYSLOG_REGEX = re.compile(r"\b([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\b")
    EPOCH_REGEX = re.compile(r"\b(1\d{9}(?:\.\d+)?)\b")

    # Severity keyword extractor
    SEVERITY_REGEX = re.compile(SEV_PAT, re.IGNORECASE)

    def parse_timestamp(self, text: str) -> Optional[Tuple[datetime, str]]:
        """Try parsing timestamps from line text."""
        # 1. ISO 8601
        iso_match = self.ISO_REGEX.search(text)
        if iso_match:
            raw = iso_match.group(1)
            clean_raw = raw.replace("Z", "+00:00").replace(" ", "T")
            try:
                dt = datetime.fromisoformat(clean_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt, raw
            except ValueError:
                pass

        # 2. Syslog format (assumes current year)
        syslog_match = self.SYSLOG_REGEX.search(text)
        if syslog_match:
            raw = syslog_match.group(1)
            try:
                current_year = datetime.now().year
                dt_str = f"{current_year} {raw}"
                dt = datetime.strptime(dt_str, "%Y %b %d %H:%M:%S")
                dt = dt.replace(tzinfo=timezone.utc)
                return dt, raw
            except ValueError:
                pass

        # 3. Epoch timestamp
        epoch_match = self.EPOCH_REGEX.search(text)
        if epoch_match:
            raw = epoch_match.group(1)
            try:
                dt = datetime.fromtimestamp(float(raw), tz=timezone.utc)
                return dt, raw
            except (ValueError, OSError):
                pass

        return None

    def extract_severity(self, text: str) -> str:
        """Extract event severity or default to INFO."""
        match = self.SEVERITY_REGEX.search(text)
        if match:
            val = match.group(1).upper()
            if val.startswith("WARN"):
                return "WARN"
            if val.startswith("DEPLOY"):
                return "DEPLOY"
            return val
        return "INFO"

    def parse_line(self, line: str, source_name: str) -> Optional[Event]:
        """Parse log line into an Event struct."""
        line = line.strip()
        if not line:
            return None

        parsed_ts = self.parse_timestamp(line)
        if not parsed_ts:
            return None

        dt, raw_ts = parsed_ts
        severity = self.extract_severity(line)

        # Message is clean content after removing raw timestamp if possible
        msg = line.replace(raw_ts, "").strip(" :-[]")
        if not msg:
            msg = line

        return Event(
            timestamp=dt,
            raw_timestamp=raw_ts,
            source=source_name,
            severity=severity,
            message=msg,
        )


class ServiceTimeline:
    """Combines and orders events from multiple log streams."""

    def __init__(self) -> None:
        self.parser = EventParser()
        self.events: List[Event] = []

    def load_log_file(self, file_path: Path, source_alias: Optional[str] = None) -> int:
        """Load and parse log file events."""
        source_name = source_alias or file_path.name
        count = 0

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                event = self.parser.parse_line(line, source_name)
                if event:
                    self.events.append(event)
                    count += 1

        return count

    def get_timeline(
        self,
        min_severity: str = "DEBUG",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keyword: Optional[str] = None,
    ) -> List[Event]:
        """Filter and sort events chronologically."""
        min_level = SEVERITY_LEVELS.get(min_severity.upper(), 0)

        filtered = []
        for e in self.events:
            e_level = SEVERITY_LEVELS.get(e.severity, 20)
            if e_level < min_level:
                continue
            if start_time and e.timestamp < start_time:
                continue
            if end_time and e.timestamp > end_time:
                continue
            if keyword:
                kw = keyword.lower()
                msg_in = kw in e.message.lower()
                src_in = kw in e.source.lower()
                if not msg_in and not src_in:
                    continue
            filtered.append(e)

        # Sort chronologically by timestamp
        filtered.sort(key=lambda x: x.timestamp)
        return filtered


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Merge multiple log files into a unified incident timeline."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "logs", nargs="+", type=Path, help="Log files to parse and merge"
    )
    parser.add_argument(
        "--min-severity",
        default="INFO",
        help=("Minimum severity level (DEBUG, INFO, WARN, ERROR, CRITICAL)"),
    )
    parser.add_argument("--keyword", help="Filter events matching keyword")
    parser.add_argument(
        "--json", action="store_true", help="Output timeline in JSON format"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Service Timeline Utility."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    timeline = ServiceTimeline()
    total_loaded = 0

    for log_path in parsed.logs:
        if log_path.exists():
            loaded = timeline.load_log_file(log_path)
            total_loaded += loaded
        else:
            print(f"Warning: File '{log_path}' not found.", file=sys.stderr)

    events = timeline.get_timeline(
        min_severity=parsed.min_severity, keyword=parsed.keyword
    )

    if parsed.json:
        serializable = []
        for e in events:
            d = asdict(e)
            d["timestamp"] = e.timestamp.isoformat()
            serializable.append(d)
        print(json.dumps(serializable, indent=2))
    else:
        print(f"=== Service Incident Timeline ({len(events)} events) ===")
        if not events:
            print("No events matched criteria.")
            return 0

        for e in events:
            ts_str = e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts_str}] [{e.severity:^8}] [{e.source:^15}] {e.message}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

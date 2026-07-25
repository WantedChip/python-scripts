"""Event Listing Scraper and Parser.

Parses event listings from JSON-LD schema, iCalendar (.ics), and HTML feeds.
Provides filtering by date range, category, and venue location,
and exports results to ICS, Markdown, or JSON.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import datetime
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple


@dataclass
class Event:
    """Represents a standardized event schema."""

    title: str
    start_date: str  # ISO string YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
    end_date: Optional[str] = None
    location: str = "TBD"
    category: str = "General"
    description: str = ""
    url: str = ""

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Convert event object to dictionary."""
        return asdict(self)


class SimpleHTMLParser(HTMLParser):
    """Basic HTML parser to extract JSON-LD scripts and event containers."""

    def __init__(self) -> None:
        super().__init__()
        self.in_script = False
        self.script_type = ""
        self.json_ld_scripts: List[str] = []
        self.html_events: List[Dict[str, str]] = []
        self._current_tag = ""
        self._current_data = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        is_event_class = "event" in attr_dict.get("class", "").lower()
        if tag == "script" and attr_dict.get("type") == "application/ld+json":
            self.in_script = True
        elif tag in ("article", "div", "li") and is_event_class:
            self._current_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_script:
            self.in_script = False
            if self._current_data.strip():
                self.json_ld_scripts.append(self._current_data.strip())
            self._current_data = ""

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self._current_data += data


def parse_iso_date(date_str: str) -> Optional[datetime.datetime]:
    """Parse various ISO date strings into datetime objects."""
    if not date_str:
        return None
    clean_str = date_str.replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
        "%Y%m%dT%H%M%SZ",
        "%Y%m%dT%H%M%S",
        "%Y%m%d",
    ):
        try:
            return datetime.datetime.strptime(clean_str[:19], fmt[:19])
        except ValueError:
            continue
    return None


def parse_json_ld(content: str) -> List[Event]:
    """Extract events from JSON-LD content."""
    events: List[Event] = []
    parser = SimpleHTMLParser()
    parser.feed(content)

    json_blocks = parser.json_ld_scripts
    if not json_blocks and content.strip().startswith(("{", "[")):
        json_blocks = [content]

    for block in json_blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Event":
                loc = item.get("location")
                loc_name = "TBD"
                if isinstance(loc, dict):
                    loc_street = loc.get("address", {}).get("streetAddress", "TBD")
                    loc_name = loc.get("name") or loc_street
                elif isinstance(loc, str):
                    loc_name = loc

                cat = item.get("category") or item.get("genre") or "General"
                if isinstance(cat, list):
                    cat = ", ".join(str(c) for c in cat)

                end_d = str(item.get("endDate", "")) if item.get("endDate") else None

                event = Event(
                    title=str(item.get("name", "Untitled Event")),
                    start_date=str(item.get("startDate", "")),
                    end_date=end_d,
                    location=loc_name,
                    category=str(cat),
                    description=str(item.get("description", "")),
                    url=str(item.get("url", "")),
                )
                events.append(event)
    return events


def parse_ical(content: str) -> List[Event]:
    """Extract events from iCalendar (.ics) format string."""
    events: List[Event] = []
    vevents = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", content, re.DOTALL)

    for vevent in vevents:
        fields = {}
        for line in vevent.splitlines():
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                key_clean = key.split(";")[0]
                fields[key_clean] = val

        if "SUMMARY" in fields:
            event = Event(
                title=fields.get("SUMMARY", "Untitled Event"),
                start_date=fields.get("DTSTART", ""),
                end_date=fields.get("DTEND"),
                location=fields.get("LOCATION", "TBD"),
                category=fields.get("CATEGORIES", "General"),
                description=fields.get("DESCRIPTION", ""),
                url=fields.get("URL", ""),
            )
            events.append(event)
    return events


def parse_events(content: str, feed_type: str = "auto") -> List[Event]:
    """Master parse method supporting auto-detection."""
    if feed_type == "ical" or "BEGIN:VCALENDAR" in content:
        return parse_ical(content)
    is_json = (
        feed_type == "jsonld"
        or "application/ld+json" in content
        or content.strip().startswith(("{", "["))
    )
    if is_json:
        return parse_json_ld(content)

    # Try JSON-LD first, fallback to ical
    parsed = parse_json_ld(content)
    if not parsed:
        parsed = parse_ical(content)
    return parsed


def filter_events(
    events: List[Event],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
) -> List[Event]:
    """Filter list of events by date range, category, and location."""
    filtered = events

    start_dt = parse_iso_date(start_date) if start_date else None
    end_dt = parse_iso_date(end_date) if end_date else None

    if start_dt:
        filtered = [
            e
            for e in filtered
            if (e_dt := parse_iso_date(e.start_date)) and e_dt >= start_dt
        ]
    if end_dt:
        filtered = [
            e
            for e in filtered
            if (e_dt := parse_iso_date(e.start_date)) and e_dt <= end_dt
        ]
    if category:
        cat_lower = category.lower()
        filtered = [e for e in filtered if cat_lower in e.category.lower()]
    if location:
        loc_lower = location.lower()
        filtered = [e for e in filtered if loc_lower in e.location.lower()]

    return filtered


def export_markdown(events: List[Event]) -> str:
    """Generate Markdown report for events."""
    lines = ["# Event Listings", "", f"Total Events: {len(events)}", ""]
    for idx, event in enumerate(events, 1):
        lines.append(f"## {idx}. {event.title}")
        lines.append(f"- **Start:** {event.start_date}")
        if event.end_date:
            lines.append(f"- **End:** {event.end_date}")
        lines.append(f"- **Location:** {event.location}")
        lines.append(f"- **Category:** {event.category}")
        if event.url:
            lines.append(f"- **URL:** [{event.url}]({event.url})")
        if event.description:
            lines.append(f"\n{event.description}\n")
        lines.append("---")
    return "\n".join(lines)


def export_ics(events: List[Event]) -> str:
    """Generate iCalendar (.ics) text for events."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//EventListingScraper//EN",
    ]
    now_str = datetime.datetime.now().strftime("%Y%m%d")
    for idx, event in enumerate(events, 1):
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:event-{idx}@{now_str}")
        lines.append(f"SUMMARY:{event.title}")
        dt_start = event.start_date.replace("-", "").replace(":", "")
        lines.append(f"DTSTART:{dt_start}")
        if event.end_date:
            dt_end = event.end_date.replace("-", "").replace(":", "")
            lines.append(f"DTEND:{dt_end}")
        lines.append(f"LOCATION:{event.location}")
        lines.append(f"CATEGORIES:{event.category}")
        if event.description:
            lines.append(f"DESCRIPTION:{event.description}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\n".join(lines)


def export_json(events: List[Event]) -> str:
    """Generate JSON string for events."""
    return json.dumps([e.to_dict() for e in events], indent=2)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Scrape and filter event listings."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--url", help="URL of event feed/page")
    parser.add_argument("--file", help="Path to local file containing feed content")
    parser.add_argument(
        "--feed-type",
        choices=["auto", "jsonld", "ical"],
        default="auto",
        help="Feed format type",
    )
    parser.add_argument("--start-date", help="Filter start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="Filter end date (YYYY-MM-DD)")
    parser.add_argument("--category", help="Filter category substring")
    parser.add_argument("--location", help="Filter location substring")
    parser.add_argument(
        "--export-format",
        choices=["md", "ics", "json"],
        default="md",
        help="Export format",
    )
    parser.add_argument("--output", help="Output file path")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point for event-listing-scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    content = ""
    if parsed.file:
        with open(parsed.file, "r", encoding="utf-8") as f:
            content = f.read()
    elif parsed.url:
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(parsed.url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:  # nosec B310
                content = resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError, ValueError) as err:
            print(f"Error fetching URL: {err}", file=sys.stderr)
            return 1
    else:
        print("Please provide --url or --file", file=sys.stderr)
        return 1

    events = parse_events(content, parsed.feed_type)
    filtered = filter_events(
        events,
        start_date=parsed.start_date,
        end_date=parsed.end_date,
        category=parsed.category,
        location=parsed.location,
    )

    if parsed.export_format == "md":
        output_str = export_markdown(filtered)
    elif parsed.export_format == "ics":
        output_str = export_ics(filtered)
    else:
        output_str = export_json(filtered)

    if parsed.output:
        with open(parsed.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Exported {len(filtered)} events to {parsed.output}")
    else:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())

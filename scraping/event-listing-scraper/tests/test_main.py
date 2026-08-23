"""Unit tests for Event Listing Scraper."""

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from typing import Any, List
from unittest.mock import MagicMock, patch

from main import (
    Event,
    build_parser,
    export_ics,
    export_json,
    export_markdown,
    filter_events,
    main,
    parse_events,
    parse_ical,
    parse_iso_date,
    parse_json_ld,
)


def _urlopen_result(payload: str, status: int = 200) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = payload.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


class TestEventListingScraper(unittest.TestCase):

    def setUp(self):
        self.sample_json_ld = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@type": "Event",
            "name": "Tech Conference 2026",
            "startDate": "2026-09-15T09:00:00",
            "endDate": "2026-09-16T17:00:00",
            "location": {
                "@type": "Place",
                "name": "Convention Center"
            },
            "category": "Technology",
            "description": "Annual tech summit"
        }
        </script>
        </head>
        </html>
        """

        self.sample_ical = """
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Python Workshop
DTSTART:20261001T100000Z
DTEND:20261001T120000Z
LOCATION:Online / Zoom
CATEGORIES:Education
DESCRIPTION:Hands-on Python coding session
END:VEVENT
END:VCALENDAR
        """

    def test_parse_json_ld(self):
        events = parse_json_ld(self.sample_json_ld)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "Tech Conference 2026")
        self.assertEqual(events[0].location, "Convention Center")
        self.assertEqual(events[0].category, "Technology")

    def test_parse_ical(self):
        events = parse_ical(self.sample_ical)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "Python Workshop")
        self.assertEqual(events[0].location, "Online / Zoom")

    def test_filter_events(self):
        e1 = Event("E1", "2026-05-01", location="New York", category="Music")
        e2 = Event("E2", "2026-06-01", location="Boston", category="Tech")
        events = [e1, e2]

        filtered_date = filter_events(events, start_date="2026-05-15")
        self.assertEqual(len(filtered_date), 1)
        self.assertEqual(filtered_date[0].title, "E2")

        filtered_cat = filter_events(events, category="music")
        self.assertEqual(len(filtered_cat), 1)
        self.assertEqual(filtered_cat[0].title, "E1")

    def test_exports(self):
        e = Event("Test", "2026-08-01", location="Room A")
        md = export_markdown([e])
        self.assertIn("# Event Listings", md)
        self.assertIn("Test", md)

        ics = export_ics([e])
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("SUMMARY:Test", ics)

        json_out = export_json([e])
        self.assertIn('"title": "Test"', json_out)


class TestParseIsoDate(unittest.TestCase):
    """Date parsing helpers used by the filter engine."""

    def test_empty_and_unparseable_strings_return_none(self) -> None:
        self.assertIsNone(parse_iso_date(""))
        self.assertIsNone(parse_iso_date("not-a-date"))

    def test_supported_formats_are_parsed(self) -> None:
        cases = {
            "2026-09-15T09:00:00+02:00": "tz-aware",
            "2026-09-15T09:00:00": "seconds",
            "2026-09-15T09:00": "minutes",
            "2026-09-15": "date-only",
            "20261001T100000Z": "ical utc",
            "20261001T100000": "ical local",
            "20261001": "ical date",
        }
        for value in cases:
            with self.subTest(format=cases[value]):
                self.assertIsNotNone(parse_iso_date(value))


class TestParseJsonLdVariants(unittest.TestCase):
    """JSON-LD extraction variants and malformed input handling."""

    def test_raw_json_array_payload_is_accepted(self) -> None:
        raw = json.dumps(
            [
                {"@type": "Event", "name": "Raw A", "startDate": "2026-01-01"},
                {"@type": "Event", "name": "Raw B", "startDate": "2026-02-01"},
            ]
        )
        events = parse_json_ld(raw)
        self.assertEqual([e.title for e in events], ["Raw A", "Raw B"])

    def test_malformed_json_block_is_skipped(self) -> None:
        html = (
            "<html><script type='application/ld+json'>{broken json!!}"
            "</script></html>"
        )
        self.assertEqual(parse_json_ld(html), [])

    def test_location_as_plain_string(self) -> None:
        raw = (
            '[{"@type": "Event", "name": "Gig", "location": "The Roxy", '
            '"startDate": "2026-03-03"}]'
        )
        events = parse_json_ld(raw)
        self.assertEqual(events[0].location, "The Roxy")

    def test_street_address_used_when_place_name_missing(self) -> None:
        raw = (
            '{"@type": "Event", "name": "Meetup", "startDate": "2026-04-04", '
            '"location": {"address": {"streetAddress": "5 Main St"}}}'
        )
        events = parse_json_ld(raw)
        self.assertEqual(events[0].location, "5 Main St")

    def test_category_list_is_joined(self) -> None:
        raw = (
            '[{"@type": "Event", "name": "Expo", "startDate": "2026-05-05", '
            '"category": ["Tech", "Business"]}]'
        )
        events = parse_json_ld(raw)
        self.assertEqual(events[0].category, "Tech, Business")

    def test_genre_fallback_and_defaults(self) -> None:
        raw = (
            '[{"@type": "Event", "name": "Plain", "genre": "Music", '
            '"endDate": "2026-06-06"}]'
        )
        events = parse_json_ld(raw)
        self.assertEqual(events[0].category, "Music")
        self.assertEqual(events[0].end_date, "2026-06-06")
        self.assertEqual(events[0].start_date, "")
        self.assertEqual(events[0].location, "TBD")


class TestParseIcalDetails(unittest.TestCase):
    """iCalendar parsing details."""

    def test_events_without_summary_are_ignored(self) -> None:
        content = (
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260101T000000Z\n"
            "END:VEVENT\nEND:VCALENDAR"
        )
        self.assertEqual(parse_ical(content), [])

    def test_parameterised_keys_and_url_field(self) -> None:
        content = (
            "BEGIN:VEVENT\nSUMMARY:Lecture\n"
            "DTSTART;TZID=Europe/Berlin:20260701T180000\n"
            "URL:https://events.example.com/lecture\nEND:VEVENT"
        )
        events = parse_ical(content)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "Lecture")
        self.assertEqual(events[0].url, "https://events.example.com/lecture")


class TestParseEventsAutoDetection(unittest.TestCase):
    """Master parser dispatch logic."""

    ICS = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Auto ICS\r\nEND:VEVENT"
    JSONLD = '[{"@type": "Event", "name": "Auto JSON", "startDate": "2026-01-01"}]'

    def test_vcalendar_content_routes_to_ical_parser(self) -> None:
        events = parse_events(self.ICS)
        self.assertEqual(events[0].title, "Auto ICS")

    def test_explicit_feed_type_overrides_detection(self) -> None:
        events = parse_events(self.JSONLD, feed_type="jsonld")
        self.assertEqual(events[0].title, "Auto JSON")

    def test_bare_vevent_falls_back_from_jsonld_to_ical(self) -> None:
        events = parse_events("BEGIN:VEVENT\nSUMMARY:Bare\nEND:VEVENT")
        self.assertEqual(events[0].title, "Bare")

    def test_unknown_content_yields_no_events(self) -> None:
        self.assertEqual(parse_events("hello world, nothing here"), [])


class TestFilterEventsRanges(unittest.TestCase):
    """Date-range, category and location filtering."""

    def _events(self) -> List[Event]:
        return [
            Event("A", "2026-05-01", location="New York", category="Music"),
            Event("B", "2026-06-15", location="Boston", category="Tech"),
            Event(
                "C",
                "2026-07-20",
                location="New York Expo Center",
                category="Music Tech",
            ),
        ]

    def test_end_date_filter_inclusive(self) -> None:
        filtered = filter_events(self._events(), end_date="2026-06-30")
        self.assertEqual([e.title for e in filtered], ["A", "B"])

    def test_combined_date_range_narrows_to_one(self) -> None:
        filtered = filter_events(
            self._events(), start_date="2026-06-01", end_date="2026-06-30"
        )
        self.assertEqual([e.title for e in filtered], ["B"])

    def test_location_substring_case_insensitive(self) -> None:
        filtered = filter_events(self._events(), location="york")
        self.assertEqual([e.title for e in filtered], ["A", "C"])

    def test_events_with_unparseable_dates_are_dropped(self) -> None:
        events = [Event("Bad", "", location="X")]
        self.assertEqual(filter_events(events, start_date="2020-01-01"), [])
        self.assertEqual(filter_events(events, end_date="2030-01-01"), [])


class TestExportFormatting(unittest.TestCase):
    """Markdown and ICS export branches."""

    def setUp(self) -> None:
        self.event = Event(
            "Full Event",
            "2026-08-01T10:00:00",
            end_date="2026-08-02T18:00:00",
            location="Hall 9",
            category="Science",
            description="An event with everything set.",
            url="https://events.example.com/full",
        )

    def test_markdown_includes_all_fields(self) -> None:
        md = export_markdown([self.event])
        self.assertIn("- **End:** 2026-08-02T18:00:00", md)
        self.assertIn(
            "[https://events.example.com/full](https://events.example.com/full)", md
        )
        self.assertIn("An event with everything set.", md)
        self.assertIn("Total Events: 1", md)

    def test_ics_includes_dtend_description_and_uid(self) -> None:
        ics = export_ics([self.event])
        self.assertIn("UID:event-1@", ics)
        self.assertIn("DTSTART:20260801T100000", ics)
        self.assertIn("DTEND:20260802T180000", ics)
        self.assertIn("DESCRIPTION:An event with everything set.", ics)

    def test_export_json_matches_dataclass_shape(self) -> None:
        payload: Any = json.loads(export_json([self.event]))
        self.assertEqual(payload[0]["title"], "Full Event")
        self.assertEqual(payload[0]["category"], "Science")


class TestEventListingCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    SAMPLE_JSONLD = (
        '<script type="application/ld+json">[{"@type": "Event", '
        '"name": "CLI Conf", "startDate": "2026-09-15T09:00:00", '
        '"location": "Web", "category": "Tech"}]</script>'
    )

    def test_build_parser_defaults(self) -> None:
        args = build_parser().parse_args(["--file", "x.html"])
        self.assertEqual(args.feed_type, "auto")
        self.assertEqual(args.export_format, "md")
        self.assertIsNone(args.start_date)
        self.assertIsNone(args.output)

    def _run_main(self, argv: List[str]) -> tuple:
        """Run main() capturing stdout/stderr; return (code, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_main_requires_source(self) -> None:
        code, _, err = self._run_main([])
        self.assertEqual(code, 1)
        self.assertIn("Please provide --url or --file", err)

    def test_main_reads_file_filters_and_prints_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            feed_path = os.path.join(tmpdir, "feed.html")
            with open(feed_path, "w", encoding="utf-8") as f:
                f.write(self.SAMPLE_JSONLD)
            argv = ["--file", feed_path, "--category", "tech"]
            code, out, _ = self._run_main(argv)
        self.assertEqual(code, 0)
        self.assertIn("# Event Listings", out)
        self.assertIn("## 1. CLI Conf", out)
        self.assertIn("**Location:** Web", out)

    def test_main_fetches_url_and_exports_json_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "events.json")
            argv = [
                "--url",
                "https://events.example.com/feed",
                "--export-format",
                "json",
                "--output",
                out_path,
            ]
            with patch(
                "main.urllib.request.urlopen",
                return_value=_urlopen_result(self.SAMPLE_JSONLD),
            ):
                code, out, _ = self._run_main(argv)
            self.assertEqual(code, 0)
            self.assertIn(f"Exported 1 events to {out_path}", out)
            with open(out_path, encoding="utf-8") as f:
                saved: Any = json.load(f)
            self.assertEqual(saved[0]["title"], "CLI Conf")

    def test_main_url_error_returns_exit_code_one(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            code, _, err = self._run_main(["--url", "https://events.example.com/x"])
        self.assertEqual(code, 1)
        self.assertIn("Error fetching URL:", err)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the Service Timeline Utility."""

import contextlib
import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple
from unittest import mock

from main import Event, EventParser, ServiceTimeline, build_parser, main


class TestServiceTimeline(unittest.TestCase):

    def setUp(self):
        self.parser = EventParser()
        self.timeline = ServiceTimeline()

    def test_parse_iso_timestamp(self):
        line = "2026-07-24T19:30:20Z [ERROR] Database connection failed"
        event = self.parser.parse_line(line, "app.log")
        self.assertIsNotNone(event)
        if event:
            self.assertEqual(event.severity, "ERROR")
            self.assertEqual(event.timestamp.year, 2026)
            self.assertIn("Database connection failed", event.message)

    def test_parse_syslog_timestamp(self):
        line = "Jul 24 19:30:20 web-server-1 systemd[1]: Service restarted RESTART"
        event = self.parser.parse_line(line, "syslog.log")
        self.assertIsNotNone(event)
        if event:
            self.assertEqual(event.severity, "RESTART")
            self.assertEqual(event.timestamp.month, 7)
            self.assertEqual(event.timestamp.day, 24)

    def test_merge_and_sort_multiple_logs(self):
        f1 = tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8")
        f2 = tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8")
        with f1, f2:
            f1.write("2026-07-24T10:00:00Z [INFO] System started\n")
            f1.write("2026-07-24T12:00:00Z [ERROR] Crash detected\n")

            f2.write("2026-07-24T11:00:00Z [WARN] High memory usage\n")

            p1, p2 = Path(f1.name), Path(f2.name)

        try:
            self.timeline.load_log_file(p1, "log1")
            self.timeline.load_log_file(p2, "log2")

            events = self.timeline.get_timeline(min_severity="INFO")
            self.assertEqual(len(events), 3)

            # Check chronological order
            self.assertEqual(events[0].severity, "INFO")
            self.assertEqual(events[1].severity, "WARN")
            self.assertEqual(events[2].severity, "ERROR")

        finally:
            if p1.exists():
                p1.unlink()
            if p2.exists():
                p2.unlink()


class TestTimestampParsing(unittest.TestCase):
    """Timestamp parser branches for every supported format."""

    def setUp(self) -> None:
        self.parser = EventParser()

    def test_epoch_timestamp_is_parsed(self) -> None:
        """Bare epoch seconds convert to an aware UTC datetime."""
        result = self.parser.parse_timestamp("1753385400 job finished")
        self.assertIsNotNone(result)
        dt, raw = result  # type: ignore[misc]
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(raw, "1753385400")
        self.assertEqual(dt.year, 2025)

    def test_invalid_iso_falls_through_to_none(self) -> None:
        """ISO-looking strings with impossible fields yield no timestamp."""
        self.assertIsNone(self.parser.parse_timestamp("2026-13-45T99:99:99Z junk"))

    def test_invalid_syslog_date_falls_through_to_none(self) -> None:
        """Syslog-shaped strings with impossible dates yield no timestamp."""
        self.assertIsNone(self.parser.parse_timestamp("Xyz 99 25:61:61 nothing"))

    def test_text_without_any_timestamp_returns_none(self) -> None:
        """Plain prose without recognizable timestamps returns None."""
        self.assertIsNone(self.parser.parse_timestamp("no temporal info here"))


class TestSeverityAndLineParsing(unittest.TestCase):
    """Severity extraction and parse_line edge cases."""

    def setUp(self) -> None:
        self.parser = EventParser()

    def test_severity_aliases_are_normalized(self) -> None:
        """WARNING collapses to WARN and DEPLOYMENT collapses to DEPLOY."""
        self.assertEqual(self.parser.extract_severity("disk WARNING near full"), "WARN")
        self.assertEqual(self.parser.extract_severity("Deployment completed"), "DEPLOY")
        self.assertEqual(self.parser.extract_severity("all good here"), "INFO")

    def test_blank_and_untimestamped_lines_are_skipped(self) -> None:
        """Empty lines and lines lacking timestamps produce no events."""
        self.assertIsNone(self.parser.parse_line("", "src"))
        self.assertIsNone(self.parser.parse_line("   \n", "src"))
        self.assertIsNone(self.parser.parse_line("nothing to see", "src"))

    def test_message_fallback_keeps_full_line(self) -> None:
        """A line that is only a timestamp keeps itself as the message."""
        event = self.parser.parse_line("2026-07-24T10:00:00Z", "solo.log")
        self.assertIsNotNone(event)
        if event:
            self.assertEqual(event.message, "2026-07-24T10:00:00Z")


class TestTimelineFiltering(unittest.TestCase):
    """Filtering combinations in get_timeline."""

    def make_event(
        self,
        hour: int,
        severity: str = "INFO",
        message: str = "body",
        source: str = "app.log",
    ) -> Event:
        """Build a synthetic event at a fixed date and given hour."""
        return Event(
            timestamp=datetime(2026, 8, 1, hour, tzinfo=timezone.utc),
            raw_timestamp=f"2026-08-01T{hour:02d}:00:00",
            source=source,
            severity=severity,
            message=message,
        )

    def setUp(self) -> None:
        self.timeline = ServiceTimeline()
        self.timeline.events = [
            self.make_event(9, "DEBUG", "cache warm"),
            self.make_event(10, "ERROR", "disk full"),
            self.make_event(11, "INFO", "deploy done", source="ci.log"),
            self.make_event(12, "WEIRD", "odd severity"),
        ]

    def test_min_severity_filters_lower_levels(self) -> None:
        """Events below the requested level are excluded."""
        events = self.timeline.get_timeline(min_severity="ERROR")
        self.assertEqual([e.severity for e in events], ["ERROR"])

    def test_unknown_min_severity_includes_everything(self) -> None:
        """An unrecognized floor defaults to zero and keeps all events."""
        events = self.timeline.get_timeline(min_severity="NOPE")
        self.assertEqual(len(events), 4)

    def test_time_window_filters_bound_events(self) -> None:
        """start_time/end_time bound the returned window inclusively."""
        start = datetime(2026, 8, 1, 10, tzinfo=timezone.utc)
        end = datetime(2026, 8, 1, 11, tzinfo=timezone.utc)
        hours = [
            e.timestamp.hour
            for e in self.timeline.get_timeline(
                min_severity="DEBUG", start_time=start, end_time=end
            )
        ]
        self.assertEqual(hours, [10, 11])

    def test_keyword_matches_message_or_source(self) -> None:
        """Keyword search hits either the message body or source name."""
        by_msg = self.timeline.get_timeline(keyword="DISK")
        self.assertEqual([e.message for e in by_msg], ["disk full"])
        by_src = self.timeline.get_timeline(keyword="ci.log")
        self.assertEqual([e.message for e in by_src], ["deploy done"])


class TestParser(unittest.TestCase):
    """CLI argument parsing tests."""

    def test_requires_at_least_one_log_file(self) -> None:
        """One or more log paths are required positionally."""
        parsed = build_parser().parse_args(["a.log"])
        self.assertEqual(parsed.min_severity, "INFO")
        self.assertIsNone(parsed.keyword)
        self.assertFalse(parsed.json)
        multi = build_parser().parse_args(
            ["a.log", "b.log", "--min-severity", "CRITICAL", "--keyword", "disk"]
        )
        self.assertEqual([str(p) for p in multi.logs], ["a.log", "b.log"])
        self.assertEqual(multi.min_severity, "CRITICAL")
        self.assertEqual(multi.keyword, "disk")


class TestMainCli(unittest.TestCase):
    """End-to-end CLI tests over temporary log files."""

    LOG_LINES = (
        "2026-07-24T09:00:00Z [DEBUG] warming caches\n"
        "2026-07-24T10:00:00Z [ERROR] disk failure imminent\n"
        "Jul 24 11:30:00 host deploy-bot Deployment finished\n"
    )

    @staticmethod
    def write_log(content: str) -> str:
        """Write ``content`` to a temp file and return its path."""
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        )
        handle.write(content)
        handle.close()
        return handle.name

    def capture(self, argv: List[str]) -> Tuple[int, str, str]:
        """Run main() capturing stdout/stderr; cleans first temp input."""
        out_buf, err_buf = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out_buf):
                with contextlib.redirect_stderr(err_buf):
                    code = main(argv)
        finally:
            candidate = argv[0]
            if os.path.exists(candidate):
                os.unlink(candidate)
        return code, out_buf.getvalue(), err_buf.getvalue()

    def test_table_output_lists_sorted_events(self) -> None:
        """Default output prints the timeline header and INFO+ events."""
        path = self.write_log(self.LOG_LINES)
        code, out, _ = self.capture([path])
        self.assertEqual(code, 0)
        self.assertIn("=== Service Incident Timeline (2 events) ===", out)
        self.assertIn("[ ERROR  ]", out)
        self.assertIn("[ DEPLOY ]", out)
        self.assertIn("disk failure imminent", out)
        self.assertNotIn("warming caches", out)

    def test_json_output_is_parseable(self) -> None:
        """--json emits an array of serialized events."""
        path = self.write_log(self.LOG_LINES)
        code, out, _ = self.capture([path, "--json", "--min-severity", "ERROR"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(len(payload), 2)  # ERROR plus DEPLOY (level 45)
        self.assertEqual(payload[0]["severity"], "ERROR")
        self.assertEqual(payload[1]["severity"], "DEPLOY")
        self.assertIn("T", payload[0]["timestamp"])

    def test_keyword_and_missing_file_handling(self) -> None:
        """Missing files warn on stderr; keyword narrows matches."""
        real_path = self.write_log(self.LOG_LINES)
        code, out, err = self.capture([real_path, "ghost.log", "--keyword", "disk"])
        self.assertEqual(code, 0)
        self.assertIn("Warning: File 'ghost.log' not found.", err)
        self.assertIn("(1 events)", out)

    def test_no_matching_events_message(self) -> None:
        """Overly strict filters report an empty timeline gracefully."""
        path = self.write_log(self.LOG_LINES)
        code, out, _ = self.capture([path, "--min-severity", "CRITICAL"])
        self.assertEqual(code, 0)
        self.assertIn("No events matched criteria.", out)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program renders the merged timeline."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        sample = self.write_log(self.LOG_LINES)
        buffer = io.StringIO()
        argv = [entry, sample]
        try:
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as ctx:
                        runpy.run_path(entry, run_name="__main__")
        finally:
            if os.path.exists(sample):
                os.unlink(sample)
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Service Incident Timeline", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

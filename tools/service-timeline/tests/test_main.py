import tempfile
import unittest
from pathlib import Path

from main import EventParser, ServiceTimeline


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


if __name__ == "__main__":
    unittest.main()

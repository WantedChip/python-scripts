"""Unit tests for Log Analyzer."""

import datetime
import os
import sys
import tempfile
import unittest

# Workaround for hyphenated folder module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error,wrong-import-position
import log_analyzer


class TestLogAnalyzer(unittest.TestCase):
    """Test suite for log_analyzer functions."""

    def test_parse_timestamp(self) -> None:
        """Test timestamp parsing under normal and fallback conditions."""
        # Standard Python logging format
        dt = log_analyzer.parse_timestamp("2026-07-08 12:00:00,123", "%Y-%m-%d %H:%M:%S,%f")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 7)
        self.assertEqual(dt.day, 8)
        self.assertEqual(dt.hour, 12)
        self.assertEqual(dt.microsecond, 123000)

        # Standard Common Log format timezone stripping fallback
        dt = log_analyzer.parse_timestamp("10/Oct/2000:13:55:36 -0700", "%d/%b/%Y:%H:%M:%S %z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2000)
        self.assertEqual(dt.month, 10)
        self.assertEqual(dt.day, 10)

        # Invalid format
        self.assertIsNone(log_analyzer.parse_timestamp("invalid", "%Y-%m-%d"))

    def test_normalize_message(self) -> None:
        """Test message parameter replacement."""
        msg = "Failed connection to 192.168.1.100:8080 from process 0x7f3e1a"
        norm = log_analyzer.normalize_message(msg)
        self.assertEqual(norm, "Failed connection to <IP>:<NUM> from process <HEX>")

        msg2 = "User 'johndoe' loaded item 123-abc-456 in 4.56 seconds"
        norm2 = log_analyzer.normalize_message(msg2)
        # Note: 'johndoe' is replaced by <STR>, 123, 456, 4.56 are replaced by <NUM>
        self.assertIn("<STR>", norm2)
        self.assertIn("<NUM>", norm2)

    def test_auto_detect_format(self) -> None:
        """Test format guessing from log snippets."""
        python_lines = [
            "2026-07-08 12:00:00,123 - INFO - main - Application started",
            "2026-07-08 12:00:01,234 - ERROR - db - Connection timed out",
        ]
        fmt_name, _ = log_analyzer.auto_detect_format(python_lines)
        self.assertEqual(fmt_name, "python")

        combined_lines = [
            '127.0.0.1 - - [08/Jul/2026:12:00:00 +0000] "GET /index.html HTTP/1.1" 200 1024 "-" "Mozilla/5.0"',
            '127.0.0.1 - - [08/Jul/2026:12:00:01 +0000] "POST /login HTTP/1.1" 500 234 "-" "Mozilla/5.0"',
        ]
        fmt_name, _ = log_analyzer.auto_detect_format(combined_lines)
        self.assertEqual(fmt_name, "combined")

    def test_analyze_spikes(self) -> None:
        """Test spike detection math."""
        # Generate constant timestamps (no spikes)
        base = datetime.datetime(2026, 7, 8, 12, 0, 0)
        timestamps = [base + datetime.timedelta(seconds=i * 10) for i in range(100)]
        spikes = log_analyzer.analyze_spikes(timestamps, window_minutes=5, threshold_stddev=2.0)
        self.assertEqual(len(spikes), 0)

        # Generate a big cluster (spike)
        spiky_timestamps = []
        # Normal traffic: 1 event every 10 seconds (6 per minute) for 15 minutes
        for minute in range(15):
            for sec in range(0, 60, 10):
                spiky_timestamps.append(base + datetime.timedelta(minutes=minute, seconds=sec))
        # Spike traffic: 100 events in minute 5
        for _ in range(100):
            spiky_timestamps.append(base + datetime.timedelta(minutes=5, seconds=12))

        spiky_timestamps.sort()
        spikes = log_analyzer.analyze_spikes(spiky_timestamps, window_minutes=1, threshold_stddev=2.0)
        self.assertGreater(len(spikes), 0)
        # The spike bucket (minute 5) should be in the results
        spike_starts = [s[0] for s in spikes]
        expected_spike_minute = base + datetime.timedelta(minutes=5)
        self.assertIn(expected_spike_minute, spike_starts)

    def test_analyze_log_file(self) -> None:
        """Test parsing end-to-end with temporary files."""
        log_content = (
            "2026-07-08 12:00:00,100 - INFO - main - started\n"
            "2026-07-08 12:00:01,200 - ERROR - main - fail connection 0x12\n"
            "2026-07-08 12:00:02,300 - ERROR - main - fail connection 0x34\n"
            "2026-07-08 12:00:03,400 - WARNING - main - disk almost full\n"
        )
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".log") as f:
            f.write(log_content)
            temp_path = f.name

        try:
            results = log_analyzer.analyze_log(temp_path, fmt_type="python")
            summary = results["summary"]
            self.assertEqual(summary["total_lines"], 4)
            self.assertEqual(summary["errors"], 2)
            self.assertEqual(summary["warnings"], 1)

            errors = results["errors"]
            self.assertEqual(len(errors), 1)  # Two connection errors normalized to one group
            self.assertEqual(errors[0]["count"], 2)
            self.assertEqual(errors[0]["normalized"], "fail connection <HEX>")
            self.assertEqual(errors[0]["sample"], "fail connection 0x12")
        finally:
            os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()

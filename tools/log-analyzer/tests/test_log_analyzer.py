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

    def test_parse_timestamp_fallback_fail(self) -> None:
        """Test parse_timestamp fallback parse failures."""
        self.assertIsNone(log_analyzer.parse_timestamp("bad_timestamp", "%Y-%m-%d"))
        # Fallback split check failures
        self.assertIsNone(log_analyzer.parse_timestamp("bad split", "%Y-%m-%d"))

    def test_auto_detect_format_none(self) -> None:
        """Test auto_detect_format returns None on unrecognized formats."""
        fmt, pat = log_analyzer.auto_detect_format(["random line", "another random line"])
        self.assertIsNone(fmt)
        self.assertIsNone(pat)

    def test_read_log_file_unknown_pattern(self) -> None:
        """Test read_log_file yields UNKNOWN level when pattern is None."""
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write("hello\n\nworld\n")
            temp_path = tmp.name

        try:
            entries = list(log_analyzer.read_log_file(temp_path, None, 0, 0, 0, None))
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["level"], "UNKNOWN")
            self.assertEqual(entries[0]["message"], "hello")
        finally:
            os.remove(temp_path)

    def test_read_log_file_status_code(self) -> None:
        """Test HTTP status code conversion when level_idx is 0."""
        # 200 -> INFO, 404 -> WARNING, 500 -> ERROR
        import re
        pat = re.compile(log_analyzer.LOG_FORMATS["common"][0])
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write(
                '127.0.0.1 - - [01/Jan/2026:00:00:00 +0000] "GET / HTTP/1.1" 200 1234\n'
                '127.0.0.1 - - [01/Jan/2026:00:00:00 +0000] "GET / HTTP/1.1" 404 1234\n'
                '127.0.0.1 - - [01/Jan/2026:00:00:00 +0000] "GET / HTTP/1.1" 500 1234\n'
            )
            temp_path = tmp.name

        try:
            entries = list(log_analyzer.read_log_file(temp_path, pat, 2, 0, 4, "%d/%b/%Y:%H:%M:%S %z"))
            self.assertEqual(len(entries), 3)
            self.assertEqual(entries[0]["level"], "INFO")
            self.assertEqual(entries[1]["level"], "WARNING")
            self.assertEqual(entries[2]["level"], "ERROR")
        finally:
            os.remove(temp_path)

    def test_analyze_spikes_edge_cases(self) -> None:
        """Test analyze_spikes handling empty list and standard deviation equals zero."""
        self.assertEqual(log_analyzer.analyze_spikes([], 5, 2.0), [])
        
        # Zero standard deviation (identical volume in all buckets)
        now = datetime.datetime.now()
        timestamps = [now, now, now + datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=10)]
        self.assertEqual(log_analyzer.analyze_spikes(timestamps, 5, 2.0), [])

    def test_analyze_log_errors(self) -> None:
        """Test analyze_log raising FileNotFoundError on invalid file path."""
        with self.assertRaises(FileNotFoundError):
            log_analyzer.analyze_log("nonexistent_log_file_123.log")

    def test_print_report(self) -> None:
        """Test print_report prints correct logs without errors."""
        import io
        from unittest.mock import patch
        
        results = {
            "summary": {
                "file_path": "test.log",
                "total_lines": 100,
                "parsed_lines": 90,
                "errors": 5,
                "warnings": 10
            },
            "errors": [
                {
                    "normalized": "error message",
                    "count": 5,
                    "sample": "error message",
                    "first_seen": "2026-01-01T00:00:00",
                    "last_seen": "2026-01-01T00:05:00",
                    "lines": [1, 2, 3]
                }
            ],
            "spikes": [
                {
                    "start": "2026-01-01T00:00:00",
                    "end": "2026-01-01T00:05:00",
                    "count": 5,
                    "stddevs_above": 3.5
                }
            ]
        }
        
        f = io.StringIO()
        with patch('sys.stdout', new=f):
            log_analyzer.print_report(results)
        
        output = f.getvalue()
        self.assertIn("LOG ANALYSIS REPORT", output)
        self.assertIn("TOP ERROR GROUPS", output)
        self.assertIn("DETECTED SPIKES", output)

    def test_main_cli_execution(self) -> None:
        """Test main function CLI entry point scenarios."""
        # 1. File not found exits 1
        with self.assertRaises(SystemExit) as exc:
            log_analyzer.main(["nonexistent_log_123.log"])
        self.assertEqual(exc.exception.code, 1)

        # 2. Valid run with json output
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write("2026-01-01 00:00:00 - INFO - main - hello\n")
            temp_path = tmp.name

        try:
            # Succeeded run does not call sys.exit, so it completes without raising SystemExit
            log_analyzer.main([temp_path, "--type", "python", "--json-output"])
        finally:
            os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for log-file-analyzer main module."""

import os
import tempfile
import unittest

from main import analyze_log_file, parse_log_line


class TestLogFileAnalyzer(unittest.TestCase):
    """Test suite for Log File Analyzer."""

    def setUp(self) -> None:
        self.sample_log_line = (
            "192.168.1.10 - - [24/Jul/2026:14:32:10 +0000] "
            '"GET /index.html HTTP/1.1" 200 4520 '
            '"http://example.com" "Mozilla/5.0"'
        )

    def test_parse_log_line_combined_format(self) -> None:
        """Test regex parsing of a Combined Log Format line."""
        entry = parse_log_line(self.sample_log_line)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["ip"], "192.168.1.10")
        self.assertEqual(entry["method"], "GET")
        self.assertEqual(entry["path"], "/index.html")
        self.assertEqual(entry["status"], 200)
        self.assertEqual(entry["bytes"], 4520)

    def test_analyze_log_file(self) -> None:
        """Test analyzing a log file with multiple lines."""
        lines = [
            (
                "192.168.1.10 - - [24/Jul/2026:14:32:10 +0000] "
                '"GET /index.html HTTP/1.1" 200 1000 "-" "-"'
            ),
            (
                "192.168.1.10 - - [24/Jul/2026:14:32:11 +0000] "
                '"GET /about.html HTTP/1.1" 200 2000 "-" "-"'
            ),
            (
                "10.0.0.5 - - [24/Jul/2026:14:32:12 +0000] "
                '"POST /login HTTP/1.1" 404 500 "-" "-"'
            ),
        ]

        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp:
            tmp.write("\n".join(lines))
            tmp_path = tmp.name

        try:
            summary = analyze_log_file(tmp_path)
            self.assertEqual(summary["total_requests"], 3)
            self.assertEqual(summary["total_bandwidth_bytes"], 3500)
            self.assertEqual(summary["top_ips"]["192.168.1.10"], 2)
            self.assertEqual(summary["top_ips"]["10.0.0.5"], 1)
            self.assertEqual(summary["status_codes"][200], 2)
            self.assertEqual(summary["status_codes"][404], 1)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()

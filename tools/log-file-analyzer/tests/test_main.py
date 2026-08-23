"""Unit tests for log-file-analyzer main module."""

import csv
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict

from main import (
    analyze_log_file,
    build_parser,
    export_csv,
    export_json,
    main,
    parse_log_line,
    print_dashboard_summary,
)


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


class TestParseEdgeCases(unittest.TestCase):
    """Test suite for malformed and partial log lines."""

    def test_garbage_line_returns_none(self) -> None:
        """Lines that do not match the combined format parse to None."""
        self.assertIsNone(parse_log_line("this is not a log line"))
        self.assertIsNone(parse_log_line(""))

    def test_dash_byte_count_parses_to_zero(self) -> None:
        line = (
            "10.0.0.9 - - [24/Jul/2026:10:00:00 +0000] "
            '"HEAD /health HTTP/1.1" 204 - "-" "-"'
        )
        entry = parse_log_line(line)
        assert entry is not None
        self.assertEqual(entry["bytes"], 0)
        self.assertEqual(entry["method"], "HEAD")

    def test_malformed_request_falls_back_to_unknown(self) -> None:
        line = "10.0.0.9 - - [24/Jul/2026:10:00:00 +0000] " '"- 404 5" 200 12'
        entry = parse_log_line(line)
        assert entry is not None
        self.assertEqual(entry["method"], "-")
        self.assertEqual(entry["path"], "404")


class TestAnalyzeEdgeCases(unittest.TestCase):
    """Test suite for aggregation over imperfect log files."""

    def _write_lines(self, lines: list) -> str:
        fd, tmp_path = tempfile.mkstemp(suffix=".log")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        self.addCleanup(lambda: os.path.exists(tmp_path) and os.remove(tmp_path))
        return tmp_path

    def test_unparsed_and_blank_lines_are_counted(self) -> None:
        tmp_path = self._write_lines(
            [
                (
                    "192.168.1.10 - - [24/Jul/2026:14:32:10 +0000] "
                    '"GET /index.html HTTP/1.1" 200 1000 "-" "-"'
                ),
                "",
                "total garbage here",
            ]
        )
        summary: Dict[str, Any] = analyze_log_file(tmp_path)
        self.assertEqual(summary["total_requests"], 1)
        self.assertEqual(summary["unparsed_lines"], 1)

    def test_dashboard_summary_output(self) -> None:
        tmp_path = self._write_lines(
            [
                (
                    "192.168.1.10 - - [24/Jul/2026:14:32:10 +0000] "
                    '"GET /index.html HTTP/1.1" 500 1000 "-" "-"'
                ),
                "bad line",
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_dashboard_summary(analyze_log_file(tmp_path))
        out = buf.getvalue()
        self.assertIn("WEB SERVER LOG ANALYSIS DASHBOARD", out)
        self.assertIn("HTTP 500", out)
        self.assertIn("/index.html", out)
        self.assertIn("Unparsed Lines    : 1", out)


class TestExportsAndCli(unittest.TestCase):
    """Test suite for JSON/CSV exports and the main() entry point."""

    SAMPLE = (
        "192.168.1.10 - - [24/Jul/2026:14:32:10 +0000] "
        '"GET /index.html HTTP/1.1" 200 1000 "-" "-"'
    )

    def setUp(self) -> None:
        fd, self.log_path = tempfile.mkstemp(suffix=".log")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(self.SAMPLE + "\n")
        self.work_dir = Path(tempfile.mkdtemp())
        self.addCleanup(
            lambda: os.path.exists(self.log_path) and os.remove(self.log_path)
        )
        self.addCleanup(lambda: shutil.rmtree(self.work_dir, ignore_errors=True))

    def test_export_json_round_trip(self) -> None:
        out_file = self.work_dir / "summary.json"
        export_json(analyze_log_file(self.log_path), str(out_file))
        data: Dict[str, Any] = json.loads(out_file.read_text(encoding="utf-8"))
        self.assertEqual(data["total_requests"], 1)
        self.assertEqual(data["status_codes"]["200"], 1)

    def test_export_csv_sections(self) -> None:
        out_file = self.work_dir / "summary.csv"
        export_csv(analyze_log_file(self.log_path), str(out_file))
        with open(out_file, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], ["Section", "Key", "Value"])
        self.assertIn(["Overview", "Total Requests", "1"], rows)
        self.assertIn(["StatusCode", "HTTP 200", "1"], rows)
        self.assertTrue(any(r[0] == "TopIP" for r in rows))
        self.assertTrue(any(r[0] == "TopPath" for r in rows))

    def test_build_parser_accepts_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["access.log"])
        self.assertEqual(args.logfile, "access.log")
        self.assertIsNone(args.json)
        self.assertIsNone(args.csv)

    def test_main_missing_file_returns_one(self) -> None:
        rc = main([str(self.work_dir / "missing.log")])
        self.assertEqual(rc, 1)

    def test_main_exports_reports_and_returns_zero(self) -> None:
        json_out = self.work_dir / "out.json"
        csv_out = self.work_dir / "out.csv"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([self.log_path, "--json", str(json_out), "--csv", str(csv_out)])
        self.assertEqual(rc, 0)
        self.assertTrue(json_out.exists())
        self.assertTrue(csv_out.exists())
        self.assertIn(f"Exported JSON report to '{json_out}'.", buf.getvalue())
        self.assertIn(f"Exported CSV report to '{csv_out}'.", buf.getvalue())

    def test_main_plain_run_prints_dashboard(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([self.log_path])
        self.assertEqual(rc, 0)
        self.assertIn("WEB SERVER LOG ANALYSIS DASHBOARD", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

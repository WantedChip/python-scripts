"""Unit tests for large-file-finder."""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from main import (
    build_parser,
    format_bytes,
    format_report_console,
    main,
    parse_size_string,
    scan_large_files,
)


class TestLargeFileFinder(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.scan_dir = Path(self.temp_dir) / "data"
        self.scan_dir.mkdir()

        # Create files of varying sizes
        self.small_file = self.scan_dir / "small.txt"
        self.small_file.write_bytes(b"A" * 500)  # 500 B

        self.large_file = self.scan_dir / "large.bin"
        self.large_file.write_bytes(b"B" * (2 * 1024 * 1024))  # 2 MB

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_parse_size_string(self):
        self.assertEqual(parse_size_string("100"), 100)
        self.assertEqual(parse_size_string("1KB"), 1024)
        self.assertEqual(parse_size_string("10MB"), 10 * 1024 * 1024)
        self.assertEqual(parse_size_string("1.5GB"), int(1.5 * 1024 * 1024 * 1024))

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500 B")
        self.assertEqual(format_bytes(1024 * 1024), "1.00 MB")

    def test_scan_large_files(self):
        files, summary = scan_large_files(self.scan_dir, min_size_bytes=1 * 1024 * 1024)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["filename"], "large.bin")
        self.assertIn(".bin", summary)
        self.assertEqual(summary[".bin"]["count"], 1)

    def test_scan_top_n(self):
        # Create another large file
        another_large = self.scan_dir / "huge.dat"
        another_large.write_bytes(b"C" * (5 * 1024 * 1024))

        files, _ = scan_large_files(self.scan_dir, min_size_bytes=1, top_n=1)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["filename"], "huge.dat")


class TestSizeParsing(unittest.TestCase):
    """Test suite for size-string parsing edge cases."""

    def test_numeric_passthrough(self) -> None:
        """Plain numbers bypass string parsing."""
        self.assertEqual(parse_size_string(2048), 2048)
        self.assertEqual(parse_size_string(1.5), 1)

    def test_bare_number_and_space_unit(self) -> None:
        self.assertEqual(parse_size_string("512"), 512)
        self.assertEqual(parse_size_string("2 kb"), 2048)

    def test_invalid_size_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_size_string("not-a-size")

    def test_unknown_unit_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_size_string("10XB")

    def test_format_bytes_terabyte_and_petabyte(self) -> None:
        self.assertEqual(format_bytes(1024**4), "1.00 TB")
        self.assertIn("PB", format_bytes(3 * 1024**5))


class TestScanEdgeCases(unittest.TestCase):
    """Test suite for scan robustness against unreadable files."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        (self.temp_dir / "ok.bin").write_bytes(b"Z" * 4096)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_unreadable_file_is_skipped(self) -> None:
        """Files raising OSError during stat are skipped without aborting."""

        original_stat = Path.stat

        def selective_stat(self: Path, **kwargs: Any) -> Any:
            if self.name == "locked.bin":
                raise PermissionError("access denied")
            return original_stat(self, **kwargs)

        with patch.object(Path, "stat", selective_stat), patch(
            "main.os.walk",
            return_value=iter(
                [
                    (
                        str(self.temp_dir),
                        [],
                        ["ok.bin", "locked.bin"],
                    )
                ]
            ),
        ):
            files, summary = scan_large_files(self.temp_dir, min_size_bytes=1)

        names = [f["filename"] for f in files]
        self.assertEqual(names, ["ok.bin"])
        self.assertEqual(summary[".bin"]["count"], 1)


class TestConsoleReport(unittest.TestCase):
    """Test suite for the console report formatter."""

    def test_report_contains_tables_and_threshold(self) -> None:
        records = [
            {
                "path": "/tmp/big.iso",
                "filename": "big.iso",
                "extension": ".iso",
                "size_bytes": 2048,
                "size_readable": "2.00 KB",
            }
        ]
        summary = {
            ".iso": {
                "count": 1,
                "total_size_bytes": 2048,
                "total_size_readable": "2.00 KB",
            }
        }
        report = format_report_console(records, summary, min_size_bytes=1024)

        self.assertIn("LARGE FILE REPORT", report)
        self.assertIn("1.00 KB", report)
        self.assertIn("/tmp/big.iso", report)
        self.assertIn("EXTENSION BREAKDOWN", report)


class TestLargeFileFinderCli(unittest.TestCase):
    """End-to-end tests for build_parser and main()."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.scan_dir = Path(self.tmp_dir.name) / "data"
        self.scan_dir.mkdir()
        (self.scan_dir / "one.txt").write_bytes(b"A" * 3000)
        (self.scan_dir / "two.log").write_bytes(b"B" * 2000)
        (self.scan_dir / "tiny.txt").write_bytes(b"C" * 10)

    def test_build_parser_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--path", str(self.scan_dir)])
        self.assertEqual(args.min_size, "100MB")
        self.assertIsNone(args.top)
        self.assertEqual(args.format, "console")
        self.assertIsNone(args.output)

    def test_main_console_prints_sorted_matches(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["-p", str(self.scan_dir), "-s", "1KB"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("Found 2 files", out)
        # Sorted descending by size: one.txt before two.log
        self.assertLess(out.index("one.txt"), out.index("two.log"))

    def test_main_json_output_writes_file(self) -> None:
        out_path = Path(self.tmp_dir.name) / "report.json"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(
                [
                    "-p",
                    str(self.scan_dir),
                    "-s",
                    "1KB",
                    "--format",
                    "json",
                    "-o",
                    str(out_path),
                ]
            )
        self.assertEqual(rc, 0)
        self.assertIn(f"Report written to {out_path}", buf.getvalue())
        data: Dict[str, Any] = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(data["threshold_bytes"], 1024)
        self.assertEqual(len(data["files"]), 2)
        self.assertEqual(set(data["extension_summary"]), {".txt", ".log"})

    def test_main_csv_output_writes_rows(self) -> None:
        out_path = Path(self.tmp_dir.name) / "report.csv"
        rc = main(
            [
                "-p",
                str(self.scan_dir),
                "-s",
                "1KB",
                "--format",
                "csv",
                "-o",
                str(out_path),
            ]
        )
        self.assertEqual(rc, 0)
        lines: List[str] = out_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "Path,Filename,Extension,SizeBytes,SizeReadable")
        self.assertEqual(len(lines), 3)

    def test_main_no_matches_reports_zero(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["-p", str(self.scan_dir), "-s", "100GB"])
        self.assertEqual(rc, 0)
        self.assertIn("Found 0 files", buf.getvalue())

    def test_main_top_limit_applied(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["-p", str(self.scan_dir), "-s", "1KB", "--top", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("Found 1 files", buf.getvalue())

    def test_main_invalid_min_size_propagates_error(self) -> None:
        with self.assertRaises(ValueError):
            main(["-p", str(self.scan_dir), "-s", "bogus"])


if __name__ == "__main__":
    unittest.main()

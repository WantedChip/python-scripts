"""Tests for the Screenshot Index & Search tool."""

import contextlib
import io
import os
import runpy
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import List, Tuple
from unittest import mock

import main as si_module
from main import ScreenshotIndexer, build_parser, main


class TestScreenshotIndexer(unittest.TestCase):

    def setUp(self) -> None:
        self.indexer = ScreenshotIndexer(db_path=":memory:")

    def test_add_and_search_by_keyword(self) -> None:
        self.indexer.add_screenshot(
            filepath="img1.png",
            app_name="VSCode",
            topic="Coding",
            created_at="2026-07-20",
            mock_text="def connect_to_database(): return True",
        )
        self.indexer.add_screenshot(
            filepath="img2.png",
            app_name="Slack",
            topic="Chat",
            created_at="2026-07-21",
            mock_text="Hey team, meeting starts at 3 PM",
        )

        results = self.indexer.search(keyword="database")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].app_name, "VSCode")
        self.assertIn("connect_to_database", results[0].text_content)

    def test_search_by_app_and_date_range(self) -> None:
        self.indexer.add_screenshot(
            filepath="img1.png",
            app_name="Chrome",
            created_at="2026-07-10",
            mock_text="Python documentation",
        )
        self.indexer.add_screenshot(
            filepath="img2.png",
            app_name="Chrome",
            created_at="2026-07-22",
            mock_text="GitHub repository view",
        )

        results = self.indexer.search(
            app_name="Chrome",
            start_date="2026-07-15",
            end_date="2026-07-25",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].created_at, "2026-07-22")


class TestOcrExtraction(unittest.TestCase):
    """OCR extraction paths with mocked tesseract boundaries."""

    def setUp(self) -> None:
        self.indexer = ScreenshotIndexer(":memory:")

    def test_mock_text_short_circuits_ocr(self) -> None:
        """Explicit mock text bypasses OCR entirely."""
        self.assertEqual(
            self.indexer.extract_text_from_image("x.png", mock_text="cached"),
            "cached",
        )

    def test_fallback_message_when_pytesseract_missing(self) -> None:
        """Without pytesseract a placeholder OCR string is produced."""
        with mock.patch.object(si_module, "PYTESSERACT_AVAILABLE", False):
            out = self.indexer.extract_text_from_image("shot.png")
        self.assertEqual(out, "Mock OCR content for shot.png")

    def test_real_ocr_path_normalizes_whitespace(self) -> None:
        """With pytesseract available, OCR text is whitespace-normalized."""
        fake_img = object()
        with mock.patch.object(si_module, "PYTESSERACT_AVAILABLE", True):
            with mock.patch.object(si_module.Image, "open", return_value=fake_img):
                with mock.patch.object(
                    si_module.pytesseract,
                    "image_to_string",
                    return_value="  messy \n ocr   output\n",
                ):
                    out = self.indexer.extract_text_from_image("shot.png")
        self.assertEqual(out, "messy ocr output")

    def test_ocr_failure_returns_empty_string(self) -> None:
        """Image open failures degrade to empty text instead of raising."""
        with mock.patch.object(si_module, "PYTESSERACT_AVAILABLE", True):
            with mock.patch.object(
                si_module.Image, "open", side_effect=OSError("bad image")
            ):
                self.assertEqual(self.indexer.extract_text_from_image("bad.png"), "")


class TestIndexingBehavior(unittest.TestCase):
    """Storage behavior of add/search around dates and replacement."""

    def setUp(self) -> None:
        self.indexer = ScreenshotIndexer(":memory:")

    def test_default_created_at_is_today(self) -> None:
        """Missing created_at defaults to today's ISO date."""
        rec_id = self.indexer.add_screenshot("fresh.png", mock_text="note")
        record = self.indexer.search(keyword="note")[0]
        self.assertGreater(rec_id, 0)
        self.assertEqual(record.created_at, date.today().isoformat())

    def test_same_filepath_replaces_existing_record(self) -> None:
        """Re-indexing one path replaces rather than duplicates."""
        self.indexer.add_screenshot("dup.png", mock_text="old contents")
        self.indexer.add_screenshot("dup.png", mock_text="new contents")
        matches = self.indexer.search(keyword="contents")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].text_content, "new contents")

    def test_topic_filter_matches_case_insensitively(self) -> None:
        """Topic search ignores case on both sides."""
        self.indexer.add_screenshot("a.png", topic="Research", mock_text="paper")
        self.assertEqual(len(self.indexer.search(topic="research")), 1)
        self.assertEqual(self.indexer.search(topic="nomatch"), [])


class TestParser(unittest.TestCase):
    """Argument parser structure tests."""

    def test_index_subcommand_fields(self) -> None:
        """index requires --file and offers app/topic/date/mock options."""
        parsed = build_parser().parse_args(
            [
                "index",
                "--file",
                "shot.png",
                "--app",
                "GIMP",
                "--topic",
                "Design",
                "--date",
                "2026-08-01",
                "--mock-text",
                "hello",
            ]
        )
        self.assertEqual(parsed.command, "index")
        self.assertEqual(parsed.file, "shot.png")
        self.assertEqual(parsed.app, "GIMP")
        self.assertEqual(parsed.topic, "Design")
        self.assertEqual(parsed.date, "2026-08-01")
        self.assertEqual(parsed.mock_text, "hello")

    def test_search_subcommand_filters(self) -> None:
        """search exposes query/app/topic/date-range filters."""
        parsed = build_parser().parse_args(
            [
                "search",
                "--query",
                "invoice",
                "--app",
                "Outlook",
                "--topic",
                "Mail",
                "--start-date",
                "2026-01-01",
                "--end-date",
                "2026-12-31",
            ]
        )
        self.assertEqual(parsed.command, "search")
        self.assertEqual(parsed.query, "invoice")
        self.assertEqual(parsed.start_date, "2026-01-01")


class TestMainCli(unittest.TestCase):
    """End-to-end CLI runs against a scratch database directory."""

    def setUp(self) -> None:
        """Create a scratch cwd; cleanup tolerates open SQLite handles."""
        self.scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.scratch, True)

    def capture_main(self, argv: List[str]) -> Tuple[int, str]:
        """Run main() capturing stdout inside the scratch cwd."""
        buffer = io.StringIO()
        with contextlib.chdir(self.scratch):
            with contextlib.redirect_stdout(buffer):
                code = main(argv)
        return code, buffer.getvalue()

    def test_no_command_prints_help(self) -> None:
        """Bare invocation prints usage help."""
        code, out = self.capture_main([])
        self.assertEqual(code, 0)
        self.assertIn("usage:", out)

    def test_index_then_search_round_trip(self) -> None:
        """CLI indexing persists records findable via CLI search."""
        code_add, out_add = self.capture_main(
            [
                "index",
                "--file",
                "receipt.png",
                "--mock-text",
                "total due 42 dollars",
                "--app",
                "Preview",
            ]
        )
        code_search, out_search = self.capture_main(["search", "--query", "due"])
        self.assertEqual(code_add, 0)
        self.assertIn("Indexed screenshot #1: receipt.png", out_add)
        self.assertEqual(code_search, 0)
        self.assertIn("Found 1 matching screenshot(s):", out_search)
        self.assertIn("[Preview]", out_search)
        self.assertIn("receipt.png", out_search)
        self.assertIn("total due 42 dollars", out_search)

    def test_search_with_no_matches_reports_zero(self) -> None:
        """Searches without hits still succeed reporting zero rows."""
        code, out = self.capture_main(["search", "--query", "nothing-here"])
        self.assertEqual(code, 0)
        self.assertIn("Found 0 matching screenshot(s):", out)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program indexes a screenshot."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        buffer = io.StringIO()
        with contextlib.chdir(self.scratch):
            argv = [entry, "index", "--file", "cli.png", "--mock-text", "cli run"]
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as ctx:
                        runpy.run_path(entry, run_name="__main__")
            self.assertTrue(
                os.path.exists(os.path.join(self.scratch, "screenshots.db"))
            )
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Indexed screenshot #1", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

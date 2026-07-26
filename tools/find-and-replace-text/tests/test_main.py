"""Unit tests for Find and Replace Text."""

import tempfile
import unittest
from pathlib import Path

from main import find_and_replace_in_dir, parse_args, process_single_file


class TestFindAndReplaceText(unittest.TestCase):
    """Test suite for Find and Replace Text tool."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_process_single_file_literal(self) -> None:
        file_path = self.test_dir / "sample.txt"
        file_path.write_text("foo bar foo baz", encoding="utf-8")

        result = process_single_file(
            file_path=file_path,
            search_pattern="foo",
            replacement="qux",
            is_regex=False,
            dry_run=False,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.replacement_count, 2)
        self.assertTrue(result.was_modified)
        self.assertEqual(file_path.read_text(), "qux bar qux baz")

    def test_process_single_file_dry_run(self) -> None:
        file_path = self.test_dir / "sample.txt"
        file_path.write_text("foo bar foo", encoding="utf-8")

        result = process_single_file(
            file_path=file_path,
            search_pattern="foo",
            replacement="qux",
            is_regex=False,
            dry_run=True,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.replacement_count, 2)
        # Content in file remains unchanged in dry-run
        self.assertEqual(file_path.read_text(), "foo bar foo")
        self.assertIn("-foo bar foo", result.diff_text)
        self.assertIn("+qux bar qux", result.diff_text)

    def test_find_and_replace_regex_and_ext_filter(self) -> None:
        f1 = self.test_dir / "f1.py"
        f1.write_text("v1.0.0", encoding="utf-8")
        f2 = self.test_dir / "f2.txt"
        f2.write_text("v1.0.0", encoding="utf-8")

        summary = find_and_replace_in_dir(
            directory=self.test_dir,
            search_pattern=r"v1\.0\.(\d+)",
            replacement=r"v2.0.\1",
            extensions={".py"},
            is_regex=True,
            dry_run=False,
        )

        self.assertEqual(summary["total_scanned"], 1)
        self.assertEqual(summary["modified_files_count"], 1)
        self.assertEqual(f1.read_text(), "v2.0.0")
        self.assertEqual(f2.read_text(), "v1.0.0")

    def test_parse_args(self) -> None:
        args = parse_args(
            ["/tmp/dir", "-s", "old", "-r", "new", "--regex", "--dry-run"]
        )
        self.assertEqual(args.directory, "/tmp/dir")
        self.assertEqual(args.search, "old")
        self.assertEqual(args.replace, "new")
        self.assertTrue(args.regex)
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main()

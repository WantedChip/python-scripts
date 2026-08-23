"""Unit tests for Find and Replace Text."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from main import (
    find_and_replace_in_dir,
    is_binary_file,
    main,
    parse_args,
    process_single_file,
)


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


class TestProcessSingleFileEdgeCases(unittest.TestCase):
    """Edge-case handling for binary, undecodable, and unwritable files."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_binary_file_is_skipped(self) -> None:
        """Files containing NUL bytes are treated as binary and skipped."""
        binary = self.test_dir / "blob.bin"
        binary.write_bytes(b"PK\x00\x03payload")

        result = process_single_file(
            file_path=binary,
            search_pattern="payload",
            replacement="x",
            is_regex=False,
            dry_run=True,
        )

        self.assertIsNone(result)
        self.assertEqual(binary.read_bytes(), b"PK\x00\x03payload")

    def test_missing_file_is_treated_as_binary(self) -> None:
        """An unreadable (missing) file reports True from is_binary_file."""
        self.assertTrue(is_binary_file(self.test_dir / "ghost.txt"))

    def test_invalid_utf8_file_skipped(self) -> None:
        """Content that is not valid UTF-8 causes the file to be skipped."""
        f = self.test_dir / "latin.txt"
        f.write_bytes(b"caf\xe9 au lait")

        result = process_single_file(
            file_path=f, search_pattern="caf", replacement="tea"
        )

        self.assertIsNone(result)
        self.assertEqual(f.read_bytes(), b"caf\xe9 au lait")

    def test_read_error_warns_and_skips(self) -> None:
        """An OSError while reading prints a warning and skips the file."""
        f = self.test_dir / "locked.txt"
        f.write_text("data", encoding="utf-8")
        err_buf = io.StringIO()

        with patch.object(Path, "read_text", side_effect=OSError("locked")):
            with redirect_stderr(err_buf):
                result = process_single_file(
                    file_path=f, search_pattern="data", replacement="x"
                )

        self.assertIsNone(result)
        self.assertIn("Failed reading", err_buf.getvalue())

    def test_no_match_returns_unmodified_result(self) -> None:
        """Zero matches produce an unmodified result without diff text."""
        f = self.test_dir / "plain.txt"
        f.write_text("nothing here", encoding="utf-8")

        result = process_single_file(
            file_path=f, search_pattern="absent", replacement="x"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.replacement_count, 0)
        self.assertFalse(result.was_modified)
        self.assertEqual(result.diff_text, "")

    def test_write_failure_reports_error_and_skips(self) -> None:
        """An OSError while saving modifications warns and yields no result."""
        f = self.test_dir / "ro.txt"
        f.write_text("alpha alpha", encoding="utf-8")
        err_buf = io.StringIO()

        with patch.object(Path, "write_text", side_effect=OSError("readonly")):
            with redirect_stderr(err_buf):
                result = process_single_file(
                    file_path=f,
                    search_pattern="alpha",
                    replacement="beta",
                    dry_run=False,
                )

        self.assertIsNone(result)
        self.assertIn("Error writing", err_buf.getvalue())


class TestDirectoryTraversal(unittest.TestCase):
    """Directory-level guards and extension normalization."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_invalid_directory_raises_value_error(self) -> None:
        """A nonexistent target directory raises ValueError."""
        missing = Path(self.temp_dir.name) / "does_not_exist"
        with self.assertRaises(ValueError):
            find_and_replace_in_dir(missing, "a", "b")

    def test_dotless_extension_filter_still_matches(self) -> None:
        """Extensions given without a leading dot are normalized."""
        f1 = self.test_dir / "note.md"
        f1.write_text("old text", encoding="utf-8")
        f2 = self.test_dir / "skip.log"
        f2.write_text("old text", encoding="utf-8")

        summary = find_and_replace_in_dir(
            directory=self.test_dir,
            search_pattern="old",
            replacement="new",
            extensions={"md"},
            dry_run=False,
        )

        self.assertEqual(summary["total_scanned"], 1)
        self.assertEqual(f1.read_text(), "new text")
        self.assertEqual(f2.read_text(), "old text")
        self.assertEqual(summary["total_replacements"], 1)


class TestMainCli(unittest.TestCase):
    """End-to-end CLI behaviour including reporting and error codes."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_main_dry_run_prints_metrics_and_diff(self) -> None:
        """Dry-run mode prints metrics plus a diff preview and exits 0."""
        f = self.test_dir / "doc.txt"
        f.write_text("foo bar\n", encoding="utf-8")
        out_buf = io.StringIO()

        with redirect_stdout(out_buf):
            code = main([str(self.test_dir), "-s", "foo", "-r", "bar", "--dry-run"])

        output = out_buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", output)
        self.assertIn("Total files scanned:    1", output)
        self.assertIn("DIFF PREVIEW", output)
        self.assertIn("-foo bar", output)

    def test_main_with_ext_filter_reports_zero_matches(self) -> None:
        """Files excluded by the --ext filter are not scanned."""
        (self.test_dir / "code.py").write_text("match me\n", encoding="utf-8")
        out_buf = io.StringIO()

        with redirect_stdout(out_buf):
            code = main([str(self.test_dir), "-s", "match", "-r", "x", "--ext", ".md"])

        output = out_buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Total files scanned:    0", output)
        self.assertNotIn("DIFF PREVIEW", output)

    def test_main_invalid_directory_returns_one(self) -> None:
        """A bad target directory makes the CLI exit 1 with an error."""
        missing = self.test_dir / "gone"
        err_buf = io.StringIO()

        with redirect_stderr(err_buf):
            code = main([str(missing), "-s", "a", "-r", "b"])

        self.assertEqual(code, 1)
        self.assertIn("Error during find and replace", err_buf.getvalue())

    def test_main_invalid_regex_returns_one(self) -> None:
        """A broken regex pattern makes the CLI exit 1 gracefully."""
        target = self.test_dir / "t.txt"
        target.write_text("abc", encoding="utf-8")
        err_buf = io.StringIO()

        with redirect_stderr(err_buf):
            code = main([str(target.parent), "-s", "(", "-r", "x", "--regex"])

        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

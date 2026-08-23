"""Unit tests for Word Frequency Counter."""

import contextlib
import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List
from unittest import mock

from main import (
    filter_and_count,
    format_csv,
    format_json,
    format_table,
    load_stop_words,
    main,
    parse_args,
    tokenize,
)


class TestWordFrequencyCounter(unittest.TestCase):
    """Test suite for Word Frequency Counter."""

    def test_tokenize(self) -> None:
        text = "Hello world! This is a test, hello again."
        tokens = tokenize(text, lower=True)
        expected = [
            "hello",
            "world",
            "this",
            "is",
            "a",
            "test",
            "hello",
            "again",
        ]
        self.assertEqual(tokens, expected)

    def test_filter_and_count(self) -> None:
        tokens = ["python", "code", "python", "the", "a", "script"]
        stop_words = {"the", "a"}

        counter = filter_and_count(
            tokens, stop_words, min_length=2, ignore_stop_words=True
        )
        self.assertEqual(counter["python"], 2)
        self.assertEqual(counter["code"], 1)
        self.assertNotIn("the", counter)
        self.assertNotIn("a", counter)

    def test_format_json(self) -> None:
        counts = [("python", 5), ("code", 3)]
        json_output = format_json(counts, total_words=8)
        data = json.loads(json_output)

        self.assertEqual(data["total_tokens"], 8)
        self.assertEqual(len(data["rankings"]), 2)
        self.assertEqual(data["rankings"][0]["word"], "python")

    def test_load_custom_stop_words(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
            f.write("customword\nanotherword\n")
            temp_path = Path(f.name)

        try:
            stop_words = load_stop_words(temp_path)
            self.assertIn("customword", stop_words)
            self.assertIn("anotherword", stop_words)
            self.assertIn("the", stop_words)  # default stop words still present
        finally:
            temp_path.unlink()

    def test_parse_args(self) -> None:
        cmd_args = ["sample.txt", "--top", "5", "--format", "json", "-m", "3"]
        args = parse_args(cmd_args)
        self.assertEqual(args.input_file, "sample.txt")
        self.assertEqual(args.top, 5)
        self.assertEqual(args.format, "json")
        self.assertEqual(args.min_length, 3)


class TestTokenizeAndFilter(unittest.TestCase):
    """Additional tokenization and filtering behavior tests."""

    def test_tokenize_preserves_case_when_lower_false(self) -> None:
        """lower=False keeps the original letter casing."""
        self.assertEqual(
            tokenize("Hello HELLO hello", lower=False), ["Hello", "HELLO", "hello"]
        )

    def test_tokenize_keeps_contractions(self) -> None:
        """Apostrophes inside words are retained."""
        tokens = tokenize("Don't stop believing")
        self.assertIn("don't", tokens)

    def test_filter_respects_min_length_and_include_switch(self) -> None:
        """Short tokens are dropped; stop-word filtering can be disabled."""
        tokens = ["a", "ab", "abc"]
        strict = filter_and_count(tokens, set(), min_length=2)
        self.assertEqual(sorted(strict.elements()), ["ab", "abc"])
        keep_all = filter_and_count(["the", "zen"], {"the"}, ignore_stop_words=False)
        self.assertEqual(sorted(keep_all.elements()), ["the", "zen"])

    def test_load_stop_words_missing_file_returns_defaults_only(self) -> None:
        """A nonexistent custom stop-word file leaves defaults untouched."""
        stop_words = load_stop_words(Path("definitely-missing-stopwords.txt"))
        self.assertIn("the", stop_words)
        self.assertNotIn("customword", stop_words)


class TestFormatters(unittest.TestCase):
    """Tests for the three output formatters."""

    COUNTS = [("alpha", 6), ("beta", 2)]

    def test_format_table_renders_ranks_and_totals(self) -> None:
        """The table shows rank rows, percentages, and summary totals."""
        table = format_table(self.COUNTS, total_words=8)
        self.assertIn("Rank", table)
        expected_row = f"{1:<6} {'alpha':<24} {6:<8} {75.0:.2f}%"
        self.assertIn(expected_row, table)
        self.assertIn("Total Unique Filtered Words: 2", table)
        self.assertIn("Total Token Count:           8", table)

    def test_format_table_handles_zero_total(self) -> None:
        """Empty result sets render zero percentages safely."""
        table = format_table([], total_words=0)
        self.assertIn("Total Unique Filtered Words: 0", table)

    def test_format_csv_writes_ranked_rows(self) -> None:
        """CSV output contains a header plus one row per word."""
        csv_out = format_csv(self.COUNTS)
        lines = [ln for ln in csv_out.strip().splitlines()]
        self.assertEqual(lines[0], "Rank,Word,Count")
        self.assertEqual(lines[1], "1,alpha,6")
        self.assertEqual(lines[2], "2,beta,2")


class TestMainCli(unittest.TestCase):
    """End-to-end CLI tests using temporary input files."""

    @staticmethod
    def write_temp(content: str, suffix: str = ".txt") -> str:
        """Write ``content`` to a temp file and return its path string."""
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        )
        handle.write(content)
        handle.close()
        return handle.name

    def run_cli(self, argv: List[str]) -> tuple:
        """Run main() capturing stdout/stderr; cleans up first argument."""
        out_buf, err_buf = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out_buf):
                with contextlib.redirect_stderr(err_buf):
                    code = main(argv)
        finally:
            if os.path.exists(argv[0]):
                os.unlink(argv[0])
        return code, out_buf.getvalue(), err_buf.getvalue()

    SAMPLE = "the quick brown fox the lazy dog quick"

    def test_table_output_by_default(self) -> None:
        """Default formatting prints the ranked console table."""
        path = self.write_temp(self.SAMPLE)
        code, out, _ = self.run_cli([path])
        self.assertEqual(code, 0)
        self.assertIn("Rank", out)
        self.assertIn("quick", out)
        self.assertIn("Total Token Count:", out)

    def test_json_and_csv_formats(self) -> None:
        """--format json/csv emit parseable JSON and CSV respectively."""
        json_path = self.write_temp(self.SAMPLE)
        code, out, _ = self.run_cli([json_path, "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["rankings"][0]["word"], "quick")
        self.assertEqual(payload["total_tokens"], 6)

        csv_path = self.write_temp(self.SAMPLE)
        code, out, _ = self.run_cli([csv_path, "--format", "csv"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("Rank,Word,Count"))
        self.assertIn("1,quick,2", out)

    def test_top_limit_and_min_length_options(self) -> None:
        """--top caps rankings; -m filters shorter words."""
        path = self.write_temp("aaa bbbb ccccc aaa bbbb ccccc aaa")
        code, out, _ = self.run_cli([path, "--top", "2", "-m", "4"])
        self.assertEqual(code, 0)
        self.assertNotIn("aaa", out)
        ranked = [ln for ln in out.splitlines() if ln and ln[0].isdigit()]
        self.assertEqual(len(ranked), 2)

    def test_include_stop_words_flag_keeps_common_words(self) -> None:
        """--include-stop-words retains 'the' in the ranking."""
        path = self.write_temp("the the the zebra")
        code, out, _ = self.run_cli([path, "--include-stop-words"])
        self.assertEqual(code, 0)
        self.assertLess(out.index("the"), out.index("zebra"))

    def test_custom_stop_words_file_is_applied(self) -> None:
        """--stop-words extends the built-in list from disk."""
        text_path = self.write_temp("apple banana cherry apple")
        stop_path = self.write_temp("banana\ncherry\n", suffix=".sw")
        try:
            code, out, _ = self.run_cli([text_path, "--stop-words", stop_path])
        finally:
            os.unlink(stop_path)
        self.assertEqual(code, 0)
        self.assertIn("apple", out)
        self.assertNotIn("banana", out)

    def test_missing_input_reports_error(self) -> None:
        """Unknown input paths print an error to stderr and exit 1."""
        code, _, err = self.run_cli(["no-such-file.txt"])
        self.assertEqual(code, 1)
        self.assertIn("Error: File not found", err)

    def test_unreadable_input_reports_error(self) -> None:
        """Directories cannot be read as text and produce an error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_buf, err_buf = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out_buf):
                with contextlib.redirect_stderr(err_buf):
                    code = main([tmp_dir])
        self.assertEqual(code, 1)
        self.assertIn("Error reading file", err_buf.getvalue())

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program counts words end-to-end."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        sample = self.write_temp("echo echo delta")
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
        self.assertIn("Total Token Count", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

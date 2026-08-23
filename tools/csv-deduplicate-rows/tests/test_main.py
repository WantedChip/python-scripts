"""
Unit tests for CSV deduplicate rows tool.
"""

import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path
from typing import Any, List

from main import build_parser, deduplicate_csv, get_row_key, is_fuzzy_match, main


class TestCsvDeduplicateRows(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.input_csv = Path(self.temp_dir.name) / "input.csv"
        self.output_csv = Path(self.temp_dir.name) / "output.csv"

        with open(self.input_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "email", "name", "score"])
            writer.writerow(["1", "user@example.com", "Alice Smith", "100"])
            writer.writerow(["2", "USER@EXAMPLE.COM", "Alice S.", "105"])
            writer.writerow(["3", "bob@example.com", "Bob Jones", "90"])
            writer.writerow(["4", "user@example.com", "Alice Duplicate", "110"])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_deduplicate_keep_first(self):
        stats = deduplicate_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            key_cols=["email"],
            keep="first",
            ignore_case=False,
        )

        self.assertEqual(stats["total_rows"], 4)
        self.assertEqual(stats["retained_rows"], 3)
        self.assertEqual(stats["removed_rows"], 1)

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            emails = [r["email"] for r in rows]
            self.assertIn("user@example.com", emails)
            self.assertIn("USER@EXAMPLE.COM", emails)
            self.assertIn("bob@example.com", emails)

    def test_deduplicate_ignore_case(self):
        stats = deduplicate_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            key_cols=["email"],
            keep="first",
            ignore_case=True,
        )

        self.assertEqual(stats["retained_rows"], 2)
        self.assertEqual(stats["removed_rows"], 2)

    def test_deduplicate_keep_last(self):
        stats = deduplicate_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            key_cols=["email"],
            keep="last",
            ignore_case=False,
        )
        self.assertEqual(stats["retained_rows"], 3)

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # Row id 4 should be retained instead of row id 1 for user@example.com
            retained_ids = [r["id"] for r in rows]
            self.assertIn("4", retained_ids)
            self.assertNotIn("1", retained_ids)

    def test_fuzzy_match(self):
        seen = ["Alice Smith"]
        self.assertTrue(is_fuzzy_match("Alice Smith", seen, threshold=0.8))
        self.assertTrue(is_fuzzy_match("Alice Smyth", seen, threshold=0.8))
        self.assertFalse(is_fuzzy_match("Bob Jones", seen, threshold=0.8))

    def test_fuzzy_deduplication(self):
        stats = deduplicate_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            key_cols=["name"],
            keep="first",
            fuzzy_threshold=0.7,
        )
        self.assertLess(stats["retained_rows"], stats["total_rows"])


def _make_csv(path: Path, rows: List[List[str]], delimiter: str = ",") -> None:
    """Writes a small CSV file for tests."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerows(rows)


class TestDeduplicateEdgeCases(unittest.TestCase):
    """Validation errors, empty inputs, delimiters, and stdout mode."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        self.input_csv = self.dir_path / "in.csv"
        _make_csv(
            self.input_csv,
            [["id", "email"], ["1", "a@x.com"], ["2", "b@x.com"]],
        )

    def test_header_only_file_reports_zero_and_skips_output(self) -> None:
        header_only = self.dir_path / "empty.csv"
        output = self.dir_path / "never.csv"
        _make_csv(header_only, [["id", "email"]])
        stats = deduplicate_csv(str(header_only), str(output), key_cols=["id"])
        self.assertEqual(
            stats, {"total_rows": 0, "retained_rows": 0, "removed_rows": 0}
        )
        self.assertFalse(output.exists())

    def test_unknown_key_column_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            deduplicate_csv(
                str(self.input_csv),
                str(self.dir_path / "o.csv"),
                key_cols=["missing"],
            )

    def test_invalid_keep_option_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            deduplicate_csv(
                str(self.input_csv),
                str(self.dir_path / "o.csv"),
                key_cols=["email"],
                keep="middle",
            )

    def test_custom_delimiter_roundtrip(self) -> None:
        semi = self.dir_path / "semi.csv"
        _make_csv(
            semi, [["id", "email"], ["1", "a@x.com"], ["2", "A@X.COM"]], delimiter=";"
        )
        out = self.dir_path / "semi_out.csv"
        stats = deduplicate_csv(
            str(semi),
            str(out),
            key_cols=["email"],
            ignore_case=True,
            delimiter=";",
        )
        self.assertEqual(stats["retained_rows"], 1)

    def test_no_output_file_streams_result_to_stdout(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            stats = deduplicate_csv(str(self.input_csv), None, key_cols=["email"])
        self.assertEqual(stats["total_rows"], 2)
        lines = [ln for ln in buffer.getvalue().splitlines() if ln]
        self.assertEqual(lines[0], "id,email")
        self.assertEqual(len(lines), 3)

    def test_all_columns_used_as_key_when_key_cols_empty(self) -> None:
        dup = self.dir_path / "dup.csv"
        _make_csv(dup, [["a", "b"], ["1", "x"], ["1", "x"], ["1", "y"]])
        stats = deduplicate_csv(str(dup), str(self.dir_path / "o.csv"))
        self.assertEqual(stats["removed_rows"], 1)

    def test_fuzzy_keep_last_retains_final_similar_row(self) -> None:
        fuzzy = self.dir_path / "fuzzy.csv"
        _make_csv(
            fuzzy,
            [
                ["id", "name"],
                ["1", "Jon Smith"],
                ["2", "John Smith"],
                ["3", "Totally Different"],
            ],
        )
        out = self.dir_path / "fuzzy_out.csv"
        stats = deduplicate_csv(
            str(fuzzy),
            str(out),
            key_cols=["name"],
            keep="last",
            fuzzy_threshold=0.8,
        )
        with open(out, newline="", encoding="utf-8") as f:
            retained_names = [r["name"] for r in csv.DictReader(f)]
        self.assertEqual(stats["retained_rows"], 2)
        self.assertIn("John Smith", retained_names)
        self.assertNotIn("Jon Smith", retained_names)


class TestGetRowKey(unittest.TestCase):
    """Key extraction rules including case folding and whitespace."""

    def test_without_key_cols_uses_every_value_in_order(self) -> None:
        row = {"b": " 2 ", "a": "1"}
        self.assertEqual(get_row_key(row, []), ("2", "1"))

    def test_ignore_case_strips_and_lowercases_string_values(self) -> None:
        row = {"name": "  Alice ", "id": "7"}
        key = get_row_key(row, ["name", "id"], ignore_case=True)
        self.assertEqual(key, ("alice", "7"))


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI runs against temporary CSV files."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        self.input_csv = self.dir_path / "people.csv"
        _make_csv(
            self.input_csv,
            [
                ["id", "email"],
                ["1", "dup@x.com"],
                ["2", "DUP@x.com"],
                ["3", "solo@x.com"],
            ],
        )

    def _run_cli(self, args: List[str]) -> Any:
        """Runs ``main`` capturing stdout/stderr; returns (code, out, err)."""
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out_buf),
            contextlib.redirect_stderr(err_buf),
        ):
            exit_code = main(args)
        return exit_code, out_buf.getvalue(), err_buf.getvalue()

    def test_cli_writes_output_and_prints_summary(self) -> None:
        output = self.dir_path / "out.csv"
        code, out, _ = self._run_cli(
            [
                "-i",
                str(self.input_csv),
                "-o",
                str(output),
                "--keys",
                "email",
                "--ignore-case",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("Total input rows  : 3", out)
        self.assertIn("Retained rows     : 2", out)
        self.assertIn("Removed duplicates: 1", out)
        self.assertIn(f"Output saved to {output}", out)
        with open(output, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([r["id"] for r in rows], ["1", "3"])

    def test_cli_stdout_mode_prints_csv_without_summary(self) -> None:
        code, out, _ = self._run_cli(["-i", str(self.input_csv)])
        self.assertEqual(code, 0)
        self.assertNotIn("Summary", out)
        self.assertIn("id,email", out)

    def test_cli_missing_input_reports_error_and_exits_one(self) -> None:
        code, _, err = self._run_cli(
            ["-i", str(self.dir_path / "ghost.csv"), "-o", "out.csv"]
        )
        self.assertEqual(code, 1)
        self.assertIn("Error deduplicating CSV:", err)

    def test_cli_bad_key_column_reports_error_and_exits_one(self) -> None:
        code, _, err = self._run_cli(
            ["-i", str(self.input_csv), "-o", "out.csv", "--keys", "nope"]
        )
        self.assertEqual(code, 1)
        self.assertIn("Error deduplicating CSV:", err)

    def test_parser_defaults_are_sensible(self) -> None:
        parsed = build_parser().parse_args(["-i", "x.csv"])
        self.assertEqual(parsed.keep, "first")
        self.assertEqual(parsed.delimiter, ",")
        self.assertFalse(parsed.ignore_case)
        self.assertIsNone(parsed.fuzzy_threshold)


if __name__ == "__main__":
    unittest.main()

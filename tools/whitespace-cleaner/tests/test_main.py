"""Unit tests for the Whitespace Cleaner utility."""

import contextlib
import csv
import io
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple
from unittest import mock

from main import (
    build_parser,
    clean_cell_whitespace,
    clean_csv_file,
    clean_text_content,
    clean_whitespace,
    main,
)


class TestWhitespaceCleaner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.txt_file = self.dir_path / "sample.txt"
        self.csv_file = self.dir_path / "sample.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_clean_cell_whitespace(self):
        self.assertEqual(clean_cell_whitespace("   hello    world   "), "hello world")
        self.assertEqual(
            clean_cell_whitespace("  col1\tcol2  ", convert_tabs=True, tab_width=4),
            "col1 col2",
        )
        self.assertEqual(
            clean_cell_whitespace("   keep   spaces   ", collapse_internal=False),
            "keep   spaces",
        )

    def test_clean_text_content(self):
        content = "  line 1   \r\n\r\n  line  2  \t  with tabs  "
        cleaned = clean_text_content(content, convert_tabs=True)
        expected = "line 1\n\nline 2 with tabs"
        self.assertEqual(cleaned, expected)

    def test_clean_csv_in_place(self):
        csv_data = [
            ["  name ", "  age  ", "  city  "],
            [" Alice ", "  30  ", " New   York "],
        ]
        with open(self.csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)

        clean_whitespace(self.csv_file, in_place=True)

        with open(self.csv_file, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))

        self.assertEqual(rows[0], ["name", "age", "city"])
        expected_row1 = ["Alice", "30", "New York"]
        self.assertEqual(rows[1], expected_row1)


class TestCellCleaning(unittest.TestCase):
    """Additional unit tests for single-cell cleaning rules."""

    def test_empty_cell_returns_empty_string(self) -> None:
        """Empty and whitespace-only inputs produce an empty result."""
        self.assertEqual(clean_cell_whitespace(""), "")

    def test_tab_expansion_with_custom_width(self) -> None:
        """Tabs advance to the next multiple of the configured width."""
        cleaned = clean_cell_whitespace(
            "a\tb", convert_tabs=True, tab_width=2, collapse_internal=False
        )
        self.assertEqual(cleaned, "a b")
        widened = clean_cell_whitespace(
            "a\tb", convert_tabs=True, tab_width=4, collapse_internal=False
        )
        self.assertEqual(widened, "a   b")

    def test_no_collapse_still_trims_ends(self) -> None:
        """Without collapsing, internal spacing stays but edges are trimmed."""
        self.assertEqual(
            clean_cell_whitespace("  x    y  ", collapse_internal=False), "x    y"
        )

    def test_newline_normalization_can_be_disabled(self) -> None:
        """With normalization off, bare carriage returns stay embedded."""
        content = "one\rtwo\nthree"
        kept = clean_text_content(content, normalize_newlines=False)
        self.assertIn("one\rtwo", kept)
        normalized = clean_text_content(content)
        self.assertNotIn("\r", normalized)
        self.assertIn("one\ntwo", normalized)


class TestCsvCleaning(unittest.TestCase):
    """Tests for CSV/TSV file processing."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_tsv(self, rows: List[List[str]]) -> Path:
        """Write tab-separated ``rows`` to a temp TSV file."""
        path = self.dir_path / "input.tsv"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerows(rows)
        return path

    def test_clean_csv_file_writes_nested_output(self) -> None:
        """Cells are cleaned and parent output directories are created."""
        source = self.write_tsv([["  a   b ", "c\t\t"], ["  spaced  ", ""]])
        target = self.dir_path / "nested" / "out.tsv"
        clean_csv_file(source, target, delimiter="\t")
        with open(target, encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t"))
        self.assertEqual(rows[0], ["a b", "c"])
        self.assertEqual(rows[1], ["spaced", ""])

    def test_auto_mode_detects_tsv_and_csv_suffixes(self) -> None:
        """.tsv/.csv suffixes select the matching delimiter automatically."""
        tsv = self.write_tsv([["  x   y ", "z"]])
        tsv_out = self.dir_path / "tsv_out.tsv"
        clean_whitespace(tsv, output_path=tsv_out)
        with open(tsv_out, encoding="utf-8", newline="") as handle:
            self.assertEqual(list(csv.reader(handle, delimiter="\t")), [["x y", "z"]])

        csv_path = self.dir_path / "sheet.csv"
        csv_out = self.dir_path / "sheet_out.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["  p   q ", " r "])
        clean_whitespace(csv_path, output_path=csv_out)
        with open(csv_out, encoding="utf-8", newline="") as handle:
            self.assertEqual(list(csv.reader(handle)), [["p q", "r"]])

    def test_explicit_text_mode_for_unknown_suffix(self) -> None:
        """Explicit --mode overrides suffix-based auto detection."""
        source = self.dir_path / "notes.log"
        source.write_text("  messy   text  \n\n  second   line \n", encoding="utf-8")
        target = self.dir_path / "cleaned.log"
        clean_whitespace(source, output_path=target, mode="text")
        self.assertEqual(
            target.read_text(encoding="utf-8"), "messy text\n\nsecond line\n"
        )

    def test_missing_output_target_raises_value_error(self) -> None:
        """Neither --in-place nor an output path is an error."""
        source = self.dir_path / "plain.txt"
        source.write_text("content", encoding="utf-8")
        with self.assertRaises(ValueError):
            clean_whitespace(source)


class TestCommandLine(unittest.TestCase):
    """CLI tests covering success, validation, and error paths."""

    @staticmethod
    def make_temp_file(directory: Path, name: str, content: str) -> Path:
        """Write ``content`` into ``directory`` and return its path."""
        path = directory / name
        path.write_text(content, encoding="utf-8")
        return path

    def run_cli(self, args_list: List[str]) -> Tuple[int, str, str]:
        """Run main() capturing stdout/stderr; caller supplies real paths."""
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf):
            with contextlib.redirect_stderr(err_buf):
                code = main(args_list)
        return code, out_buf.getvalue(), err_buf.getvalue()

    def test_parser_defaults_and_flags(self) -> None:
        """Parser exposes documented defaults and optional output."""
        parser = build_parser()
        parsed = parser.parse_args(["in.txt"])
        self.assertIsNone(parsed.output)
        self.assertFalse(parsed.in_place)
        self.assertEqual(parsed.mode, "auto")
        self.assertFalse(parsed.no_collapse)
        self.assertFalse(parsed.convert_tabs)
        self.assertEqual(parsed.tab_width, 4)
        full = parser.parse_args(
            [
                "in.txt",
                "-i",
                "--mode",
                "text",
                "--no-collapse",
                "--convert-tabs",
                "--tab-width",
                "2",
            ]
        )
        self.assertTrue(full.in_place)
        self.assertEqual(full.mode, "text")
        self.assertTrue(full.no_collapse)
        self.assertTrue(full.convert_tabs)
        self.assertEqual(full.tab_width, 2)

    def test_missing_output_argument_is_rejected(self) -> None:
        """No output and no --in-place makes argparse exit with code 2."""
        parser = build_parser()
        with mock.patch.object(sys, "argv", ["prog", "only-input.txt"]):
            with self.assertRaises(SystemExit) as ctx:
                main(["only-input.txt"])
        self.assertEqual(ctx.exception.code, 2)
        del parser

    def test_successful_text_cleaning_to_output(self) -> None:
        """A text run writes the output file and reports success."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            source = self.make_temp_file(directory, "doc.txt", "  a   b  \n")
            code, out, _ = self.run_cli([str(source), str(directory / "out.txt")])
            self.assertEqual(code, 0)
            self.assertIn("Successfully cleaned whitespace", out)
            self.assertEqual((directory / "out.txt").read_text(), "a b\n")

    def test_in_place_flag_cleans_original(self) -> None:
        """--in-place overwrites the source file itself."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            source = self.make_temp_file(directory, "note.txt", " x\ty \n")
            code, _, _ = self.run_cli(["--in-place", str(source)])
            self.assertEqual(code, 0)
            self.assertEqual(source.read_text(), "x y\n")

    def test_unreadable_input_reports_error_and_exit_one(self) -> None:
        """Missing input files surface a stderr message and exit code 1."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "ghost.txt"
            code, _, err = self.run_cli([str(missing), str(Path(tmp_dir) / "o.txt")])
        self.assertEqual(code, 1)
        self.assertIn("Error:", err)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program cleans files end-to-end."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            source = self.make_temp_file(directory, "main_in.txt", "  z   w \n")
            argv = [entry, str(source), str(directory / "main_out.txt")]
            buffer = io.StringIO()
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as ctx:
                        runpy.run_path(entry, run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Successfully cleaned whitespace", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

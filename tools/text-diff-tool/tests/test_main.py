"""Unit tests for Text Diff Tool."""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple
from unittest import mock

from main import (
    build_parser,
    calculate_diff_metrics,
    format_summary_metrics,
    generate_side_by_side_diff,
    generate_unified_diff,
    main,
)


class TestTextDiffTool(unittest.TestCase):
    """Test suite for diff generation and metric calculations."""

    def test_identical_texts(self):
        text = "line 1\nline 2\nline 3"
        metrics = calculate_diff_metrics(text, text)
        self.assertEqual(metrics["additions"], 0)
        self.assertEqual(metrics["deletions"], 0)
        self.assertEqual(metrics["modifications"], 0)
        self.assertEqual(metrics["unchanged"], 3)

    def test_additions_and_deletions(self):
        text1 = "apple\nbanana\ncherry"
        text2 = "apple\ndragonfruit\ncherry\nelderberry"
        metrics = calculate_diff_metrics(text1, text2)
        self.assertGreaterEqual(metrics["additions"], 1)

    def test_unified_diff_output(self):
        t1 = "hello\nworld"
        t2 = "hello\nthere\nworld"
        diff = generate_unified_diff(t1, t2, from_file="a", to_file="b")
        self.assertIn("--- a", diff)
        self.assertIn("+++ b", diff)
        self.assertIn("+there", diff)

    def test_side_by_side_diff_output(self):
        t1 = "line A\nline B"
        t2 = "line A\nline C"
        diff = generate_side_by_side_diff(t1, t2, width=60)
        self.assertIn("ORIGINAL", diff)
        self.assertIn("MODIFIED", diff)
        self.assertIn("line A", diff)

    def test_empty_input(self):
        metrics = calculate_diff_metrics("", "")
        self.assertEqual(metrics["unchanged"], 0)
        self.assertEqual(metrics["additions"], 0)


class TestDiffMetrics(unittest.TestCase):
    """Detailed metric accounting for every opcode category."""

    def test_pure_insertion_counted(self) -> None:
        """Inserted lines count as additions only."""
        metrics = calculate_diff_metrics("one", "one\ntwo\nthree")
        self.assertEqual(metrics["additions"], 2)
        self.assertEqual(metrics["deletions"], 0)
        self.assertEqual(metrics["modifications"], 0)
        self.assertEqual(metrics["unchanged"], 1)

    def test_pure_deletion_counted(self) -> None:
        """Removed lines count as deletions only."""
        metrics = calculate_diff_metrics("one\ntwo\nthree", "one")
        self.assertEqual(metrics["deletions"], 2)
        self.assertEqual(metrics["additions"], 0)

    def test_replacement_of_equal_length_counts_modifications(self) -> None:
        """Same-length replacements are counted as modifications."""
        metrics = calculate_diff_metrics("a\nb\nc", "a\nX\nc")
        self.assertEqual(metrics["modifications"], 1)
        self.assertEqual(metrics["unchanged"], 2)

    def test_unequal_length_replacement_splits_counts(self) -> None:
        """Replacement blocks with extra lines yield deletions or additions."""
        shrink = calculate_diff_metrics("a\nb\nc\nd", "a\nX\nd")
        self.assertEqual(shrink["modifications"], 1)
        self.assertEqual(shrink["deletions"], 1)

        grow = calculate_diff_metrics("a\nb", "a\nX\nY\nZ")
        self.assertGreaterEqual(grow["additions"], 2)
        self.assertGreaterEqual(grow["modifications"], 1)


class TestColoredDiffOutput(unittest.TestCase):
    """Tests for ANSI colored unified and side-by-side rendering."""

    T1 = "alpha\nbeta\ngamma\ndelta\nkeep"
    T2 = "alpha\nBETA2\ngamma\nnew-line"

    def test_unified_color_codes_all_line_classes(self) -> None:
        """Headers, hunks, additions and removals receive ANSI colors."""
        diff = generate_unified_diff(
            self.T1, self.T2, from_file="f1.txt", to_file="f2.txt", color=True
        )
        self.assertIn("\033[1m--- f1.txt", diff)
        self.assertIn("\033[1m+++ f2.txt", diff)
        self.assertIn("\033[36m@@", diff)
        self.assertIn("\033[32m+", diff)
        self.assertIn("\033[31m-", diff)

    def test_unified_without_color_has_no_escape_codes(self) -> None:
        """Plain mode output contains no ANSI escapes."""
        diff = generate_unified_diff(self.T1, self.T2)
        self.assertNotIn("\033[", diff)

    def test_side_by_side_replace_rows_colored_yellow(self) -> None:
        """Replaced rows render in yellow on both sides."""
        diff = generate_side_by_side_diff(
            "same\nold-value", "same\nnew-value", width=60, color=True
        )
        self.assertIn("\033[33m", diff)
        self.assertIn("new-value", diff)

    def test_side_by_side_delete_rows_colored_red(self) -> None:
        """Deleted rows render red with an empty modified column."""
        diff = generate_side_by_side_diff(
            "same\nshared-tail\ndrop-me", "same\nshared-tail", color=True
        )
        self.assertIn("\033[31m", diff)
        self.assertIn("drop-me", diff)

    def test_side_by_side_insert_rows_colored_green(self) -> None:
        """Inserted rows render green on the modified side."""
        diff = generate_side_by_side_diff("only", "only\nextra", color=True)
        self.assertIn("\033[32m", diff)
        self.assertIn("extra", diff)

    def test_long_lines_are_truncated_to_column_width(self) -> None:
        """Content wider than the column is clipped."""
        long_text = "x" * 200
        diff = generate_side_by_side_diff(long_text, long_text, width=40)
        self.assertIn("x" * 16, diff)  # col_width = (40 - 7) // 2
        self.assertNotIn("x" * 17, diff)


class TestSummaryAndParser(unittest.TestCase):
    """Tests for summary formatting and CLI parsing."""

    def test_format_summary_metrics_lists_all_counts(self) -> None:
        """Summary shows each metric plus their total."""
        summary = format_summary_metrics(
            {"additions": 4, "deletions": 2, "modifications": 6, "unchanged": 8}
        )
        self.assertIn("Additions    : 4", summary)
        self.assertIn("Deletions    : 2", summary)
        self.assertIn("Modifications: 6", summary)
        self.assertIn("Unchanged    : 8", summary)
        self.assertIn("Total Lines  : 20", summary)

    def test_parser_defaults_and_choices(self) -> None:
        """file1/file2 are positional; format defaults to unified."""
        parser = build_parser()
        parsed = parser.parse_args(["a.txt", "b.txt"])
        self.assertEqual(str(parsed.file1), "a.txt")
        self.assertEqual(str(parsed.file2), "b.txt")
        self.assertEqual(parsed.format, "unified")
        self.assertFalse(parsed.color)
        self.assertEqual(parsed.width, 80)
        side = parser.parse_args(["a.txt", "b.txt", "--format", "side-by-side"])
        self.assertEqual(side.format, "side-by-side")


class TestMainCli(unittest.TestCase):
    """End-to-end CLI tests using temporary files."""

    @staticmethod
    def write_temp(content: str, suffix: str = ".txt") -> Path:
        """Write ``content`` to a temp file and return its path."""
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        )
        handle.write(content)
        handle.close()
        return Path(handle.name)

    def run_cli(self, args_list: List[str]) -> Tuple[int, str, str]:
        """Run main() capturing stdout/stderr; cleans created files after."""
        out_buf, err_buf = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out_buf):
                with contextlib.redirect_stderr(err_buf):
                    code = main(args_list)
        finally:
            for arg in args_list[:2]:
                if os.path.exists(arg):
                    os.unlink(arg)
        return code, out_buf.getvalue(), err_buf.getvalue()

    def test_missing_input_files_return_one(self) -> None:
        """Nonexistent inputs produce an error message and exit code 1."""
        code, _, err = self.run_cli(["ghost-a.txt", "ghost-b.txt"])
        self.assertEqual(code, 1)
        self.assertIn("Error: One or both input files do not exist.", err)

    def test_unified_cli_run_prints_report_and_metrics(self) -> None:
        """Default run emits a unified diff followed by the summary block."""
        f1 = self.write_temp("alpha\nbeta\nkeep\n")
        f2 = self.write_temp("alpha\nbeta-two\nkeep\nadded\n")
        code, out, _ = self.run_cli([str(f1), str(f2)])
        self.assertEqual(code, 0)
        self.assertIn("--- Diff Summary Metrics ---", out)
        self.assertIn("+added", out)
        self.assertIn(f"--- {f1}", out)

    def test_side_by_side_cli_run_with_width_and_color(self) -> None:
        """--format side-by-side honors width and --color options."""
        f1 = self.write_temp("row-one\nshared")
        f2 = self.write_temp("row-one-changed\nshared\nfresh")
        code, out, _ = self.run_cli(
            [str(f1), str(f2), "--format", "side-by-side", "--width", "50", "--color"]
        )
        self.assertEqual(code, 0)
        self.assertIn("ORIGINAL", out)
        self.assertIn("\033[33m", out)
        self.assertIn("fresh", out)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program diffs two temp files cleanly."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        f1 = self.write_temp("one\ntwo")
        f2 = self.write_temp("one\nTWO")
        buffer = io.StringIO()
        argv = [entry, str(f1), str(f2)]
        try:
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as ctx:
                        runpy.run_path(entry, run_name="__main__")
        finally:
            os.unlink(f1)
            os.unlink(f2)
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Diff Summary Metrics", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

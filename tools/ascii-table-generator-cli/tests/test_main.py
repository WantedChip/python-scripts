import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import patch

from main import (
    BORDER_STYLES,
    build_parser,
    calculate_column_widths,
    format_cell,
    main,
    parse_data,
    render_table,
)


class TestAsciiTableGenerator(unittest.TestCase):
    """Unit tests for ASCII Table Generator functions."""

    def test_parse_csv_data(self):
        csv_input = "Name,Age,Role\nAlice,30,Engineer\nBob,25,Designer"
        rows = parse_data(csv_input, delimiter=",")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], ["Name", "Age", "Role"])
        self.assertEqual(rows[1], ["Alice", "30", "Engineer"])

    def test_parse_tsv_data(self):
        tsv_input = "Name\tAge\nAlice\t30\nBob\t25"
        rows = parse_data(tsv_input)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1], ["Alice", "30"])

    def test_calculate_column_widths(self):
        rows = [["ID", "Product Name"], ["1", "Laptop"], ["100", "Mouse"]]
        widths = calculate_column_widths(rows)
        self.assertEqual(widths, [3, 12])

    def test_format_cell_alignment(self):
        self.assertEqual(format_cell("Hi", 5, "left"), "Hi   ")
        self.assertEqual(format_cell("Hi", 5, "right"), "   Hi")
        self.assertEqual(format_cell("Hi", 5, "center"), " Hi  ")

    def test_render_table_grid(self):
        rows = [["A", "B"], ["1", "2"]]
        table = render_table(rows, style_name="grid", align="left")
        self.assertIn("+---+---+", table)
        self.assertIn("| A | B |", table)

    def test_render_table_markdown(self):
        rows = [["Header1", "Header2"], ["Val1", "Val2"]]
        table = render_table(rows, style_name="markdown", align="left")
        self.assertIn("| Header1 | Header2 |", table)
        self.assertIn("|---------|---------|", table)


class TestParseDataEdgeCases(unittest.TestCase):
    """Parsing fallbacks: emptiness, autodetection, and custom delimiters."""

    def test_blank_content_returns_no_rows(self) -> None:
        self.assertEqual(parse_data(""), [])
        self.assertEqual(parse_data("   \n \n"), [])

    def test_comma_autodetected_when_no_tabs_present(self) -> None:
        rows = parse_data("a,b\nc,d")
        self.assertEqual(rows, [["a", "b"], ["c", "d"]])

    def test_explicit_custom_delimiter(self) -> None:
        rows = parse_data("x;y;z\n1;2;3", delimiter=";")
        self.assertEqual(rows[0], ["x", "y", "z"])

    def test_quoted_cells_with_embedded_delimiter(self) -> None:
        rows = parse_data('name,score\n"Doe, Jane",99')
        self.assertEqual(rows[1], ["Doe, Jane", "99"])


class TestWidthAndCellHelpers(unittest.TestCase):
    """Boundary behaviour of width calculation and cell padding."""

    def test_widths_of_empty_matrix(self) -> None:
        self.assertEqual(calculate_column_widths([]), [])

    def test_exact_fit_cell_is_unchanged_for_all_alignments(self) -> None:
        for alignment in ("left", "right", "center"):
            self.assertEqual(format_cell("abc", 3, alignment), "abc")

    def test_center_padding_splits_evenly_when_possible(self) -> None:
        self.assertEqual(format_cell("hi", 6, "center"), "  hi  ")

    def test_oversized_text_is_never_truncated_or_padded(self) -> None:
        self.assertEqual(
            format_cell("longer-than-width", 4, "right"), "longer-than-width"
        )


class TestRenderTableStyles(unittest.TestCase):
    """Rendering rules per border style, header mode, and ragged rows."""

    def test_simple_style_has_no_borders_but_keeps_header_rule(self) -> None:
        table = render_table([["H1", "H2"], ["v1", "v2"]], style_name="simple")
        lines = table.splitlines()
        self.assertNotIn("+", table)
        self.assertEqual(lines[0], "H1   H2")
        self.assertTrue(set(lines[1]) <= {"-"})
        self.assertEqual(lines[2], "v1   v2")

    def test_fancy_style_uses_unicode_box_drawing(self) -> None:
        table = render_table([["A", "B"], ["1", "2"]], style_name="fancy")
        self.assertIn("┌───┬───┐", table)
        self.assertIn("═══", table)
        self.assertIn("│ A | B │", table)  # inner separator stays ASCII pipe
        self.assertIn("└───┴───┘", table)

    def test_unknown_style_falls_back_to_grid(self) -> None:
        fallback = render_table([["A"], ["1"]], style_name="nonexistent")
        expected = render_table([["A"], ["1"]], style_name="grid")
        self.assertEqual(fallback, expected)

    def test_grid_draws_internal_dividers_between_body_rows(self) -> None:
        table = render_table(
            [["C1", "C2"], ["r1", "r1"], ["r2", "r2"]],
            style_name="grid",
        )
        # top border, header rule, internal rule, bottom border
        self.assertEqual(table.count("+----+----+"), 4)

    def test_ragged_row_is_padded_to_table_width(self) -> None:
        table = render_table([["Long", "Header"], ["tiny"]])
        lines = table.splitlines()
        body_line = lines[-2]  # last line is the bottom border
        self.assertEqual(body_line, "| tiny |        |")

    def test_no_header_still_separates_body_rows_in_grid(self) -> None:
        table = render_table([["r1", "r1"], ["r2", "r2"]], has_header=False)
        lines = table.splitlines()
        # top border, row, internal divider, row, bottom border
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[2], "+----+----+")
        self.assertNotIn("═", table)

    def test_markdown_right_and_center_align_markers(self) -> None:
        right = render_table([["H"], ["x"]], style_name="markdown", align="right")
        self.assertIn("-:|", right.replace("--", "-"))
        center = render_table([["H"], ["x"]], style_name="markdown", align="center")
        self.assertIn(":-", center)

    def test_every_style_defines_all_border_keys(self) -> None:
        required = {
            "top_left",
            "top_mid",
            "top_right",
            "top_line",
            "mid_left",
            "mid_mid",
            "mid_right",
            "mid_line",
            "bot_left",
            "bot_mid",
            "bot_right",
            "bot_line",
            "v_line",
            "header_line",
        }
        for name, style in BORDER_STYLES.items():
            self.assertEqual(set(style), required, f"style {name} incomplete")

    def test_empty_rows_renders_empty_string(self) -> None:
        self.assertEqual(render_table([]), "")


def _run_cli(args: List[str], stdin_text: Optional[str] = None) -> Any:
    """Runs ``main`` capturing stdout/stderr/stdin; returns (code, out, err)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    stdin_patch = (
        patch("sys.stdin", io.StringIO(stdin_text))
        if stdin_text is not None
        else contextlib.nullcontext()
    )
    with stdin_patch, contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(
        err_buf
    ):
        exit_code = main(args)
    return exit_code, out_buf.getvalue(), err_buf.getvalue()


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI runs against temporary data files and stdin."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        self.csv_file = self.dir_path / "data.csv"
        self.csv_file.write_text("Name,Score\nAlice,91\nBob,84\n", encoding="utf-8")

    def test_reads_csv_from_file_and_prints_grid(self) -> None:
        code, out, _ = _run_cli(["--input", str(self.csv_file)])
        self.assertEqual(code, 0)
        self.assertIn("+-------+-------+", out)
        self.assertIn("| Name  | Score |", out)
        self.assertIn("| Alice | 91    |", out)

    def test_reads_stdin_when_no_input_given(self) -> None:
        code, out, err = _run_cli([], stdin_text="k,v\n1,2\n")
        self.assertEqual(code, 0)
        self.assertIn("| k | v |", out)
        self.assertIn("| 1 | 2 |", out)

    def test_blank_stdin_reports_no_data(self) -> None:
        code, _, err = _run_cli([], stdin_text="\n  \n")
        self.assertEqual(code, 0)
        self.assertIn("No data to display.", err)

    def test_style_align_and_delimiter_flags_are_honoured(self) -> None:
        semi_file = self.dir_path / "semi.csv"
        semi_file.write_text("id;name\n7;Zed\n", encoding="utf-8")
        code, out, _ = _run_cli(
            [
                "--input",
                str(semi_file),
                "--delimiter",
                ";",
                "--style",
                "fancy",
                "--align",
                "center",
                "--no-header",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("┌────┬──────┐", out)
        self.assertIn("│ 7  | Zed  │", out)
        self.assertNotIn("═", out)  # --no-header removes header rule

    def test_markdown_style_via_cli(self) -> None:
        code, out, _ = _run_cli(["--input", str(self.csv_file), "--style", "markdown"])
        self.assertEqual(code, 0)
        self.assertIn("| Alice | 91    |", out)
        self.assertIn("|-------|-------|", out)

    def test_parser_defaults(self) -> None:
        parsed = build_parser().parse_args([])
        self.assertIsNone(parsed.input)
        self.assertEqual(parsed.style, "grid")
        self.assertEqual(parsed.align, "left")
        self.assertFalse(parsed.no_header)


if __name__ == "__main__":
    unittest.main()

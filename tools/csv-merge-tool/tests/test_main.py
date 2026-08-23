import contextlib
import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, List

from main import build_parser, main, merge_csvs, resolve_input_files


class TestCsvMergeTool(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.file1 = self.dir_path / "a.csv"
        self.file2 = self.dir_path / "b.csv"
        self.output = self.dir_path / "output.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_csv(self, path, rows):
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)

    def _read_csv(self, path):
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            return list(reader)

    def test_merge_overlapping_headers(self):
        self._write_csv(self.file1, [["id", "name"], ["1", "Alice"]])
        self._write_csv(self.file2, [["id", "age"], ["2", "30"]])

        merge_csvs([self.file1, self.file2], self.output, default_value="N/A")
        result = self._read_csv(self.output)

        self.assertEqual(result[0], ["id", "name", "age"])
        self.assertEqual(result[1], ["1", "Alice", "N/A"])
        self.assertEqual(result[2], ["2", "N/A", "30"])

    def test_merge_tag_source(self):
        self._write_csv(self.file1, [["id"], ["100"]])
        merge_csvs([self.file1], self.output, tag_source_col="source")
        result = self._read_csv(self.output)

        self.assertEqual(result[0], ["source", "id"])
        self.assertEqual(result[1], ["a.csv", "100"])

    def test_merge_dedupe(self):
        self._write_csv(self.file1, [["id", "val"], ["1", "X"]])
        self._write_csv(self.file2, [["id", "val"], ["1", "X"]])

        merge_csvs([self.file1, self.file2], self.output, dedupe=True)
        result = self._read_csv(self.output)

        # Header + 1 row (duplicate suppressed)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1], ["1", "X"])

    def test_resolve_input_files(self):
        self._write_csv(self.file1, [["id"]])
        resolved = resolve_input_files([str(self.dir_path / "*.csv")])
        self.assertIn(self.file1, resolved)


class TestMergeCsvsEdgeCases(unittest.TestCase):
    """Error branches and less common merging options."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        self.output = self.dir_path / "out.csv"

    @staticmethod
    def _write(path: Path, rows: List[List[str]]) -> None:
        """Writes raw CSV rows to a file."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)

    def test_empty_input_list_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            merge_csvs([], self.output)

    def test_files_without_any_headers_raise_value_error(self) -> None:
        empty = self.dir_path / "empty.csv"
        empty.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            merge_csvs([empty], self.output)

    def test_headerless_rows_are_skipped_but_valid_files_still_merge(
        self,
    ) -> None:
        """An empty first file is skipped; later files still contribute."""
        empty = self.dir_path / "empty.csv"
        good = self.dir_path / "good.csv"
        empty.write_text("", encoding="utf-8")
        self._write(good, [["h"], ["v"]])
        rows = merge_csvs([empty, good], self.output)
        content = list(csv.reader(self.output.open(encoding="utf-8")))
        self.assertEqual(rows, 1)
        self.assertEqual(content, [["h"], ["v"]])

    def test_custom_default_fill_value_used_for_missing_columns(self) -> None:
        a = self.dir_path / "a.csv"
        b = self.dir_path / "b.csv"
        self._write(a, [["x"], ["1"]])
        self._write(b, [["y"], ["2"]])
        merge_csvs([a, b], self.output, default_value="-")
        content = list(csv.reader(self.output.open(encoding="utf-8")))
        self.assertEqual(content, [["x", "y"], ["1", "-"], ["-", "2"]])


class TestResolveInputFilesRules(unittest.TestCase):
    """Glob expansion ordering and de-duplication of resolved inputs."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)

    def test_plain_paths_resolve_without_globbing(self) -> None:
        target = self.dir_path / "plain.csv"
        target.write_text("h\n", encoding="utf-8")
        self.assertEqual(resolve_input_files([str(target)]), [target])

    def test_duplicate_matches_are_deduplicated(self) -> None:
        one = self.dir_path / "one.csv"
        two = self.dir_path / "two.csv"
        one.write_text("h\n", encoding="utf-8")
        two.write_text("h\n", encoding="utf-8")
        resolved = resolve_input_files([str(one), str(self.dir_path / "*.csv")])
        self.assertEqual(resolved.count(one), 1)
        self.assertIn(two, resolved)

    def test_literal_path_with_glob_metacharacters_falls_back_to_direct(
        self,
    ) -> None:
        """Filenames containing ``[]`` defeat glob matching and use direct path."""
        weird = self.dir_path / "report[1].csv"
        weird.write_text("h\n", encoding="utf-8")
        self.assertEqual(resolve_input_files([str(weird)]), [weird])


def _run_cli(args: List[str]) -> Any:
    """Runs ``main`` capturing stdout/stderr; returns (code, out, err)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        exit_code = main(args)
    return exit_code, out_buf.getvalue(), err_buf.getvalue()


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI runs against temporary CSV files."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        self.prev_cwd = os.getcwd()
        os.chdir(self.dir_path)
        self.addCleanup(os.chdir, self.prev_cwd)

    def _seed(self) -> None:
        for name in ("one.csv", "two.csv"):
            path = self.dir_path / name
            path.write_text("id,val\n1,x\n", encoding="utf-8")

    def test_cli_merges_glob_and_reports_row_count(self) -> None:
        self._seed()
        code, out, _ = _run_cli(["*.csv", "--output", "merged.csv"])
        self.assertEqual(code, 0)
        self.assertIn("Successfully merged 2 files into 'merged.csv' (2 rows).", out)
        self.assertTrue(Path("merged.csv").exists())

    def test_cli_no_matching_inputs_exits_one(self) -> None:
        code, _, err = _run_cli(["nothing_here_*.csv", "--output", "m.csv"])
        self.assertEqual(code, 1)
        self.assertIn("No matching input files found.", err)

    def test_cli_merge_error_is_reported_and_exits_one(self) -> None:
        """An empty input triggers the ValueError path inside ``main``."""
        (self.dir_path / "blank.csv").write_text("", encoding="utf-8")
        code, _, err = _run_cli(["blank.csv", "--output", "m.csv"])
        self.assertEqual(code, 1)
        self.assertIn("Error:", err)
        self.assertFalse(Path("m.csv").exists())

    def test_cli_tags_source_column_when_requested(self) -> None:
        self._seed()
        output = self.dir_path / "tagged.csv"
        code, _, _ = _run_cli(
            [str(self.dir_path / "*.csv"), "-o", str(output), "--tag-source", "src"]
        )
        self.assertEqual(code, 0)
        with open(output, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
        self.assertEqual(header, ["src", "id", "val"])

    def test_parser_requires_output_flag(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["some.csv"])


if __name__ == "__main__":
    unittest.main()

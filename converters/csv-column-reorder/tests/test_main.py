"""
Unit tests for CSV column reorder tool.
"""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import List

from main import inspect_headers, load_config, main, parse_args, process_csv


class TestCsvColumnReorder(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.input_csv = Path(self.temp_dir.name) / "input.csv"
        self.output_csv = Path(self.temp_dir.name) / "output.csv"
        self.config_json = Path(self.temp_dir.name) / "config.json"

        # Create sample CSV
        with open(self.input_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "first_name", "last_name", "age", "country"])
            writer.writerow(["1", "Alice", "Smith", "30", "USA"])
            writer.writerow(["2", "Bob", "Jones", "25", "UK"])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_inspect_headers(self):
        headers = inspect_headers(str(self.input_csv))
        self.assertEqual(headers, ["id", "first_name", "last_name", "age", "country"])

    def test_reorder_and_select_columns(self):
        target_cols = ["last_name", "first_name", "id"]
        count, out_headers = process_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            target_columns=target_cols,
        )

        self.assertEqual(count, 2)
        self.assertEqual(out_headers, ["last_name", "first_name", "id"])

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
            self.assertEqual(rows[0], ["last_name", "first_name", "id"])
            self.assertEqual(rows[1], ["Smith", "Alice", "1"])
            self.assertEqual(rows[2], ["Jones", "Bob", "2"])

    def test_missing_columns_with_defaults(self):
        target_cols = ["id", "first_name", "status", "role"]
        column_defaults = {"status": "Active"}
        count, out_headers = process_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            target_columns=target_cols,
            column_defaults=column_defaults,
            default_value="N/A",
        )

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(rows[0]["status"], "Active")
            self.assertEqual(rows[0]["role"], "N/A")

    def test_keep_extra_columns(self):
        target_cols = ["country", "id"]
        count, out_headers = process_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            target_columns=target_cols,
            keep_extra=True,
        )

        self.assertEqual(
            out_headers, ["country", "id", "first_name", "last_name", "age"]
        )

    def test_load_config(self):
        config_data = {
            "order": ["id", "country"],
            "defaults": {"status": "Pending"},
        }
        with open(self.config_json, "w", encoding="utf-8") as f:
            json.dump(config_data, f)

        order, defaults = load_config(str(self.config_json))
        self.assertEqual(order, ["id", "country"])
        self.assertEqual(defaults, {"status": "Pending"})


class TestCsvColumnReorderCli(unittest.TestCase):
    """CLI-level tests for argument parsing and end-to-end processing."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.input_csv = self.dir_path / "input.csv"
        self.output_csv = self.dir_path / "output.csv"
        self.config_json = self.dir_path / "config.json"

        with open(self.input_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name"])
            writer.writerow(["1", "Alice"])
            writer.writerow(["2", "Bob"])

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _read_output_rows(self) -> List[List[str]]:
        """Read all rows from the CLI output CSV."""
        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    def test_parse_args_defaults(self) -> None:
        """Only --input is mandatory; remaining options carry defaults."""
        args = parse_args(["-i", "data.csv", "-c", "id,name"])
        self.assertEqual(args.input, "data.csv")
        self.assertEqual(args.columns, "id,name")
        self.assertIsNone(args.output)
        self.assertIsNone(args.config)
        self.assertEqual(args.default_value, "")
        self.assertEqual(args.delimiter, ",")
        self.assertFalse(args.inspect)
        self.assertFalse(args.keep_extra)

    def test_main_writes_reordered_file(self) -> None:
        """End-to-end reorder writes the exact requested columns."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "-i",
                    str(self.input_csv),
                    "-o",
                    str(self.output_csv),
                    "-c",
                    "name,id",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("Successfully processed 2 rows", stdout.getvalue())
        self._read_output_rows()
        self.assertEqual(
            self._read_output_rows(), [["name", "id"], ["Alice", "1"], ["Bob", "2"]]
        )

    def test_main_prints_result_to_stdout_when_no_output(self) -> None:
        """Without -o the transformed CSV is streamed to stdout."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["-i", str(self.input_csv), "-c", "id"])

        self.assertEqual(exit_code, 0)
        self.assertIn("id\n1\n2", stdout.getvalue().replace("\r\n", "\n"))

    def test_main_inspect_lists_headers(self) -> None:
        """--inspect prints a numbered header listing instead of converting."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["-i", str(self.input_csv), "--inspect"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Headers in", output)
        self.assertIn("1. id", output)
        self.assertIn("2. name", output)
        self.assertFalse(self.output_csv.exists())

    def test_main_inspect_missing_file_fails(self) -> None:
        """Inspecting a nonexistent file reports the error and exits 1."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(["-i", str(self.dir_path / "missing.csv"), "--inspect"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Error inspecting CSV", stderr.getvalue())

    def test_main_requires_column_selection(self) -> None:
        """Neither --columns nor --config nor --keep-extra is an error."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(["-i", str(self.input_csv)])

        self.assertEqual(exit_code, 1)
        self.assertIn("Must specify columns", stderr.getvalue())

    def test_main_config_invalid_json_fails(self) -> None:
        """A malformed config JSON aborts processing with exit code 1."""
        self.config_json.write_text("{not-json", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "-i",
                    str(self.input_csv),
                    "-o",
                    str(self.output_csv),
                    "--config",
                    str(self.config_json),
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("Error reading config file", stderr.getvalue())

    def test_main_config_drives_order_and_defaults(self) -> None:
        """A valid config supplies both column order and default fills."""
        config_data = {"order": ["id", "missing_col"], "defaults": {"missing_col": "X"}}
        self.config_json.write_text(json.dumps(config_data), encoding="utf-8")

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "-i",
                    str(self.input_csv),
                    "-o",
                    str(self.output_csv),
                    "--config",
                    str(self.config_json),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            self._read_output_rows(), [["id", "missing_col"], ["1", "X"], ["2", "X"]]
        )

    def test_main_keep_extra_without_columns(self) -> None:
        """--keep-extra alone is a valid invocation keeping every column."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "-i",
                    str(self.input_csv),
                    "-o",
                    str(self.output_csv),
                    "--keep-extra",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            self._read_output_rows(),
            [["id", "name"], ["1", "Alice"], ["2", "Bob"]],
        )

    def test_main_processing_error_missing_input(self) -> None:
        """Processing a nonexistent input file exits 1 with an error."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "-i",
                    str(self.dir_path / "missing.csv"),
                    "-o",
                    str(self.output_csv),
                    "-c",
                    "id",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("Error processing CSV", stderr.getvalue())

    def test_main_custom_delimiter(self) -> None:
        """The delimiter option flows through parsing and writing."""
        delimited = self.dir_path / "semicolon.csv"
        delimited.write_text("id;name\n1;Alice\n", encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            exit_code = main(
                [
                    "-i",
                    str(delimited),
                    "-o",
                    str(self.output_csv),
                    "-c",
                    "name",
                    "--delimiter",
                    ";",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(self._read_output_rows(), [["name"], ["Alice"]])


if __name__ == "__main__":
    unittest.main()

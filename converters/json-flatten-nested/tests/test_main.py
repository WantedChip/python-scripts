"""
Unit tests for JSON flatten nested tool.
"""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict, List

from main import export_to_csv, flatten_dict, flatten_json_data, main, parse_args


class TestJsonFlattenNested(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_csv = Path(self.temp_dir.name) / "output.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_flatten_dict_simple(self):
        nested = {
            "user": {
                "name": "John Doe",
                "address": {
                    "city": "New York",
                    "zip": "10001",
                },
            },
            "active": True,
        }

        flat = flatten_dict(nested, sep=".")
        self.assertEqual(flat["user.name"], "John Doe")
        self.assertEqual(flat["user.address.city"], "New York")
        self.assertEqual(flat["user.address.zip"], "10001")
        self.assertTrue(flat["active"])

    def test_flatten_dict_array_indexing(self):
        nested = {
            "items": [
                {"name": "Laptop", "price": 1200},
                {"name": "Mouse", "price": 25},
            ],
            "tags": ["tech", "gadgets"],
        }

        flat = flatten_dict(nested, sep=".")
        self.assertEqual(flat["items.0.name"], "Laptop")
        self.assertEqual(flat["items.0.price"], 1200)
        self.assertEqual(flat["items.1.name"], "Mouse")
        self.assertEqual(flat["tags.0"], "tech")
        self.assertEqual(flat["tags.1"], "gadgets")

    def test_custom_separator(self):
        nested = {"a": {"b": {"c": 1}}}
        flat = flatten_dict(nested, sep="/")
        self.assertEqual(flat["a/b/c"], 1)

    def test_no_array_flattening(self):
        nested = {"user": "Alice", "hobbies": ["reading", "cycling"]}
        flat = flatten_dict(nested, sep=".", flatten_lists=False)
        self.assertEqual(flat["user"], "Alice")
        self.assertEqual(flat["hobbies"], ["reading", "cycling"])

    def test_max_depth(self):
        nested = {"a": {"b": {"c": 1}}}
        flat = flatten_dict(nested, sep=".", max_depth=1)
        self.assertEqual(flat["a"], {"b": {"c": 1}})

    def test_export_to_csv(self):
        data = [
            {"user.id": 1, "user.name": "Alice", "user.role": "Admin"},
            {"user.id": 2, "user.name": "Bob", "user.role": "User"},
        ]

        export_to_csv(data, str(self.output_csv))
        self.assertTrue(self.output_csv.exists())

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["user.name"], "Alice")
            self.assertEqual(rows[1]["user.role"], "User")


class TestFlattenJsonData(unittest.TestCase):
    """Tests for the top-level record dispatcher flatten_json_data."""

    def test_list_of_dicts_flattened_individually(self) -> None:
        """Each element of a top-level array becomes its own flat record."""
        data = [{"a": {"b": 1}}, {"c": 2}]
        records = flatten_json_data(data)
        self.assertEqual(records, [{"a.b": 1}, {"c": 2}])

    def test_scalar_items_wrapped_in_value_key(self) -> None:
        """Scalar array elements are wrapped under the 'value' key."""
        self.assertEqual(
            flatten_json_data([1, "two"]), [{"value": 1}, {"value": "two"}]
        )

    def test_single_dict_wrapped_in_list(self) -> None:
        """A single top-level object yields a one-element list."""
        records = flatten_json_data({"x": {"y": True}})
        self.assertEqual(records, [{"x.y": True}])

    def test_top_level_scalar(self) -> None:
        """A bare scalar input is wrapped as {'value': scalar}."""
        self.assertEqual(flatten_json_data(7), [{"value": 7}])

    def test_primitive_nested_value_keeps_path_key(self) -> None:
        """Non-dict/list recursion results store under the parent path."""
        self.assertEqual(flatten_dict("leaf", parent_key="k"), {"k": "leaf"})


class TestExportToCsvVariants(unittest.TestCase):
    """Cell rendering rules of export_to_csv."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_csv = Path(self.temp_dir.name) / "out.csv"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_none_and_container_values_rendered(self) -> None:
        """None renders empty; dict/list cells render as JSON strings."""
        records: List[Dict[str, Any]] = [
            {"name": "A", "note": None, "meta": {"k": 1}},
            {"name": "B", "tags": [1, "x"]},
        ]
        export_to_csv(records, str(self.output_csv))

        with open(self.output_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["note"], "")
        self.assertEqual(json.loads(rows[0]["meta"]), {"k": 1})
        self.assertEqual(json.loads(rows[1]["tags"]), [1, "x"])

    def test_stdout_export_unions_headers_in_order(self) -> None:
        """Without an output path rows stream to stdout with merged headers."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            export_to_csv([{"a": 1}, {"b": 2}], None)

        lines = stdout.getvalue().strip().splitlines()
        self.assertEqual(lines[0].replace("\r", ""), "a,b")
        self.assertIn("1,", lines[1])


class TestJsonFlattenNestedCli(unittest.TestCase):
    """CLI-level tests for parse_args and main()."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.input_json = self.dir_path / "in.json"
        self.output_file = self.dir_path / "out.csv"
        self.input_json.write_text(
            json.dumps({"user": {"name": "Ann"}, "roles": ["dev"]}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_args_defaults(self) -> None:
        """Defaults: csv format, dot separator, arrays flattened."""
        args = parse_args(["-i", "x.json"])
        self.assertIsNone(args.output)
        self.assertEqual(args.format, "csv")
        self.assertEqual(args.sep, ".")
        self.assertFalse(args.no_array_flatten)
        self.assertIsNone(args.max_depth)

    def _run_main(self, extra_args: List[str]) -> int:
        """Invoke main() capturing stdout/stderr, returning exit code."""
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["-i", str(self.input_json)] + extra_args)
        return code

    def test_main_csv_to_file(self) -> None:
        """Default csv mode writes the file and reports success."""
        code = self._run_main(["-o", str(self.output_file)])
        self.assertEqual(code, 0)
        self.assertTrue(self.output_file.exists())
        with open(self.output_file, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["user.name"], "Ann")
        self.assertEqual(rows[0]["roles.0"], "dev")

    def test_main_json_stdout_single_record_is_object(self) -> None:
        """JSON output for one input object prints a single object."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(["-i", str(self.input_json), "--format", "json"])
        self.assertEqual(code, 0)
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(parsed["user.name"], "Ann")

    def test_main_json_to_file_multiple_records(self) -> None:
        """Multiple flattened records serialize as a JSON array file."""
        self.input_json.write_text(json.dumps([{"id": 1}, {"id": 2}]), encoding="utf-8")
        target = self.dir_path / "flat.json"
        code = self._run_main(["--format", "json", "-o", str(target)])
        self.assertEqual(code, 0)
        data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data, [{"id": 1}, {"id": 2}])

    def test_main_no_array_flatten_flag(self) -> None:
        """--no-array-flatten keeps lists intact in CSV cells."""
        code = self._run_main(["-o", str(self.output_file), "--no-array-flatten"])
        self.assertEqual(code, 0)
        with open(self.output_file, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(json.loads(rows[0]["roles"]), ["dev"])

    def test_main_custom_separator(self) -> None:
        """--sep changes the nested key separator in output headers."""
        code = self._run_main(["-o", str(self.output_file), "--sep", "__"])
        self.assertEqual(code, 0)
        with open(self.output_file, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
        self.assertIn("user__name", header)

    def test_main_max_depth_flag(self) -> None:
        """--max-depth stops recursion, leaving nested values unflattened."""
        code = self._run_main(["-o", str(self.output_file), "--max-depth", "1"])
        self.assertEqual(code, 0)
        with open(self.output_file, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(json.loads(rows[0]["user"]), {"name": "Ann"})

    def test_main_missing_input_fails(self) -> None:
        """A nonexistent input returns exit code 1 with stderr message."""
        self.input_json.unlink()
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main(["-i", str(self.input_json)])
        self.assertEqual(code, 1)
        self.assertIn("Error loading JSON", stderr.getvalue())

    def test_main_invalid_json_fails(self) -> None:
        """Malformed JSON returns exit code 1."""
        self.input_json.write_text("{oops", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main(["-i", str(self.input_json)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

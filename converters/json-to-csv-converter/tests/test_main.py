import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from main import build_parser, flatten_json_object, json_to_csv, main, read_json_records


class TestJsonToCsvConverter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.json_file = self.dir_path / "input.json"
        self.jsonl_file = self.dir_path / "input.jsonl"
        self.output_file = self.dir_path / "output.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _read_csv(self):
        with open(self.output_file, "r", encoding="utf-8", newline="") as f:
            return list(csv.reader(f))

    def test_flatten_json_object(self):
        data = {
            "name": "Alice",
            "info": {"age": 30, "city": "NYC"},
            "tags": ["admin", "dev"],
        }
        flat = flatten_json_object(data)
        self.assertEqual(flat["name"], "Alice")
        self.assertEqual(flat["info.age"], 30)
        self.assertEqual(flat["info.city"], "NYC")
        self.assertEqual(flat["tags"], "admin, dev")

    def test_convert_json_array(self):
        records = [
            {"id": 1, "profile": {"role": "admin"}},
            {"id": 2, "profile": {"role": "user"}, "active": True},
        ]
        self.json_file.write_text(json.dumps(records), encoding="utf-8")

        count = json_to_csv(self.json_file, self.output_file)
        self.assertEqual(count, 2)

        rows = self._read_csv()
        self.assertEqual(rows[0], ["id", "profile.role", "active"])
        self.assertEqual(rows[1], ["1", "admin", ""])
        self.assertEqual(rows[2], ["2", "user", "True"])

    def test_convert_jsonl(self):
        lines = [
            json.dumps({"a": 1, "b": "x"}),
            json.dumps({"a": 2, "b": "y"}),
        ]
        self.jsonl_file.write_text("\n".join(lines), encoding="utf-8")

        count = json_to_csv(self.jsonl_file, self.output_file, is_jsonl=True)
        self.assertEqual(count, 2)

        rows = self._read_csv()
        self.assertEqual(rows[0], ["a", "b"])
        self.assertEqual(rows[1], ["1", "x"])
        self.assertEqual(rows[2], ["2", "y"])


class TestFlattenJsonObjectEdgeCases(unittest.TestCase):
    """Cell-level rendering rules of flatten_json_object."""

    def test_null_value_becomes_empty_string(self) -> None:
        """None values flatten to the empty string."""
        self.assertEqual(flatten_json_object({"x": None}), {"x": ""})

    def test_empty_list_becomes_empty_string(self) -> None:
        """Empty lists flatten to the empty string."""
        self.assertEqual(flatten_json_object({"tags": []}), {"tags": ""})

    def test_list_of_dicts_encoded_as_json(self) -> None:
        """Lists containing containers are stored as JSON documents."""
        flat = flatten_json_object({"items": [{"sku": "A"}, 2]})
        self.assertEqual(json.loads(flat["items"]), [{"sku": "A"}, 2])

    def test_deep_nesting_uses_separators(self) -> None:
        """Nested dicts chain keys with the separator."""
        flat = flatten_json_object({"a": {"b": {"c": {"d": 1}}}})
        self.assertEqual(flat, {"a.b.c.d": 1})


class TestReadJsonRecords(unittest.TestCase):
    """Input parsing rules for JSON and JSONL sources."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_single_top_level_object_is_one_record(self) -> None:
        """A bare JSON object is treated as a single record."""
        path = self.dir_path / "single.json"
        path.write_text('{"id": 9}', encoding="utf-8")
        records = read_json_records(path)
        self.assertEqual(records, [{"id": 9}])

    def test_non_dict_array_items_are_filtered(self) -> None:
        """Scalar entries inside a top-level array are dropped."""
        path = self.dir_path / "mixed.json"
        path.write_text('[1, {"id": 1}, "x", {"id": 2}]', encoding="utf-8")
        records = read_json_records(path)
        self.assertEqual(records, [{"id": 1}, {"id": 2}])

    def test_jsonl_suffix_detected_without_flag(self) -> None:
        """The .jsonl extension alone switches to line-by-line parsing."""
        path = self.dir_path / "data.jsonl"
        path.write_text(
            json.dumps({"a": 1}) + "\n\n" + json.dumps({"a": 2}),
            encoding="utf-8",
        )
        records = read_json_records(path)
        self.assertEqual(records, [{"a": 1}, {"a": 2}])


class TestJsonToCsvOptions(unittest.TestCase):
    """Conversion option behaviour: no-flatten, delimiters, errors."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, data: str) -> Path:
        """Write raw JSON text to a temp file and return its path."""
        path = self.dir_path / "in.json"
        path.write_text(data, encoding="utf-8")
        return path

    def test_no_records_raises_value_error(self) -> None:
        """An empty record set raises ValueError instead of writing CSV."""
        path = self._write_json("[]")
        with self.assertRaises(ValueError):
            json_to_csv(path, self.dir_path / "out.csv")

    def test_no_flatten_keeps_nested_objects(self) -> None:
        """flatten=False preserves nested structures in cells."""
        src = self._write_json('[{"id": 1, "profile": {"role": "admin"}}]')
        out = self.dir_path / "out.csv"
        count = json_to_csv(src, out, flatten=False)
        self.assertEqual(count, 1)
        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["id", "profile"])
        self.assertIn("admin", rows[1][1])

    def test_custom_delimiter_tab(self) -> None:
        """A custom delimiter is honored in both header and body."""
        src = self._write_json('[{"a": 1, "b": 2}]')
        out = self.dir_path / "out.tsv"
        json_to_csv(src, out, delimiter="\t")
        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter="\t"))
        self.assertEqual(rows[0], ["a", "b"])
        self.assertEqual(rows[1], ["1", "2"])

    def test_output_parent_dirs_created(self) -> None:
        """Missing output parent directories are created automatically."""
        src = self._write_json('{"k": "v"}')
        out = self.dir_path / "nested" / "deeper" / "out.csv"
        count = json_to_csv(src, out)
        self.assertEqual(count, 1)
        self.assertTrue(out.exists())


class TestJsonToCsvCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.input_file = self.dir_path / "in.json"
        self.output_file = self.dir_path / "out.csv"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_parser_defaults(self) -> None:
        """Positional args parse; optional flags carry defaults."""
        parser = build_parser()
        args = parser.parse_args(["a.json", "b.csv"])
        self.assertEqual(args.input, "a.json")
        self.assertEqual(args.output, "b.csv")
        self.assertFalse(args.jsonl)
        self.assertFalse(args.no_flatten)
        self.assertEqual(args.sep, ".")
        self.assertEqual(args.delimiter, ",")

    def test_main_success_message_and_output(self) -> None:
        """Successful conversion prints counts and writes the CSV."""
        self.input_file.write_text('[{"n": 1}, {"n": 2}]', encoding="utf-8")
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(self.input_file), str(self.output_file)])

        self.assertEqual(exit_code, 0)
        self.assertIn("Successfully converted 2 records", stdout.getvalue())
        self.assertTrue(self.output_file.exists())

    def test_main_empty_records_error(self) -> None:
        """Zero convertible records exit 1 with an error on stderr."""
        self.input_file.write_text("[1, 2]", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main([str(self.input_file), str(self.output_file)])

        self.assertEqual(exit_code, 1)
        self.assertIn("No valid JSON records", stderr.getvalue())
        self.assertFalse(self.output_file.exists())

    def test_main_missing_input_error(self) -> None:
        """A missing input file exits 1 via OSError handling."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(["nope.json", str(self.output_file)])

        self.assertEqual(exit_code, 1)
        self.assertIn("Error:", stderr.getvalue())

    def test_main_flags_passthrough(self) -> None:
        """--jsonl/--sep/--delimiter flags flow into conversion."""
        self.input_file.write_text('{"meta": {"page": 2}}\n', encoding="utf-8")
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    str(self.input_file),
                    str(self.output_file),
                    "--jsonl",
                    "--sep",
                    ":",
                    "-d",
                    ";",
                ]
            )

        self.assertEqual(exit_code, 0)
        with open(self.output_file, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        self.assertEqual(rows[0], ["meta:page"])


if __name__ == "__main__":
    unittest.main()

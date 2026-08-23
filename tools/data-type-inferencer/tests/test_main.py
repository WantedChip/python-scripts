import contextlib
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from main import (
    analyze_column,
    convert_value_to_typed,
    infer_single_value_type,
    is_datetime,
    is_json,
    main,
    process_dataset,
)


class TestDataTypeInferencer(unittest.TestCase):
    """Test suite for data type inferencer."""

    def test_infer_single_value_type(self) -> None:
        self.assertEqual(infer_single_value_type("123"), "integer")
        self.assertEqual(infer_single_value_type("-45.67"), "float")
        self.assertEqual(infer_single_value_type("true"), "boolean")
        self.assertEqual(infer_single_value_type("2026-07-24T12:00:00Z"), "datetime")
        self.assertEqual(infer_single_value_type('{"key": "value"}'), "json")
        self.assertEqual(infer_single_value_type("hello world"), "string")

    def test_analyze_column(self) -> None:
        int_vals = ["1", "2", "3", "4", ""]
        info = analyze_column("age", int_vals)
        self.assertEqual(info["inferred_type"], "integer")
        self.assertTrue(info["nullable"])
        self.assertEqual(info["null_count"], 1)

        enum_vals = ["RED", "BLUE", "RED", "GREEN", "BLUE", "RED"]
        info_enum = analyze_column("color", enum_vals, max_enum_cardinality=5)
        self.assertEqual(info_enum["inferred_type"], "enum")
        self.assertIn("enum_values", info_enum)

    def test_convert_value_to_typed(self) -> None:
        self.assertTrue(convert_value_to_typed("true", "boolean"))
        self.assertEqual(convert_value_to_typed("42", "integer"), 42)
        self.assertEqual(convert_value_to_typed("3.14", "float"), 3.14)
        self.assertEqual(convert_value_to_typed('{"a": 1}', "json"), {"a": 1})

    def test_process_dataset(self) -> None:
        csv_content = (
            "id,name,age,active,signup_date,payload\n"
            '1,Alice,30,true,2025-01-01,{"role": "admin"}\n'
            '2,Bob,25,false,2025-02-15,{"role": "user"}\n'
            '3,Charlie,35,true,2025-03-20,{"role": "guest"}\n'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.csv"
            schema_path = Path(tmpdir) / "schema.json"
            converted_path = Path(tmpdir) / "converted.csv"
            input_path.write_text(csv_content, encoding="utf-8")

            schema = process_dataset(
                input_file=input_path,
                schema_output=schema_path,
                converted_output=converted_path,
            )

            self.assertEqual(schema["column_count"], 6)
            self.assertTrue(schema_path.exists())
            self.assertTrue(converted_path.exists())

            schema_json = json.loads(schema_path.read_text(encoding="utf-8"))
            types = {
                col["name"]: col["inferred_type"] for col in schema_json["columns"]
            }
            self.assertEqual(types["id"], "integer")
            self.assertEqual(types["age"], "integer")
            self.assertEqual(types["active"], "boolean")
            self.assertEqual(types["signup_date"], "datetime")
            self.assertEqual(types["payload"], "json")


class TestInferenceEdges(unittest.TestCase):
    """Edge branches of the type detectors and column analysis."""

    def test_infer_single_value_empty_returns_null(self) -> None:
        self.assertEqual(infer_single_value_type("   "), "null")

    def test_is_json_malformed_returns_false(self) -> None:
        self.assertFalse(is_json("{not valid"))
        self.assertFalse(is_json("[1, 2"))
        self.assertTrue(is_json("[1, 2]"))

    def test_is_datetime_iso_offset(self) -> None:
        self.assertTrue(is_datetime("2026-08-23T10:00:00+05:00"))
        self.assertTrue(is_datetime("2026-08-23T10:00:00Z"))
        self.assertFalse(is_datetime("definitely not a date"))

    def test_analyze_column_all_null_values(self) -> None:
        result = analyze_column("empty_col", ["", "   "])
        self.assertEqual(result["inferred_type"], "string")
        self.assertTrue(result["nullable"])
        self.assertEqual(result["distinct_count"], 0)

    def test_mixed_boolean_column_reclassified(self) -> None:
        """A '1' only counts boolean when every value reads boolean."""
        result = analyze_column("mixed", ["true", "1", "maybe"])
        self.assertIn(result["inferred_type"], ("enum", "string"))

    def test_float_dominance_with_integers(self) -> None:
        result = analyze_column("nums", ["1", "2.5"])
        self.assertEqual(result["inferred_type"], "float")

    def test_too_many_distinct_becomes_string_not_enum(self) -> None:
        values = [f"value_{i}" for i in range(11)]
        result = analyze_column("wide", values, max_enum_cardinality=10)
        self.assertEqual(result["inferred_type"], "string")

    def test_convert_value_edge_cases(self) -> None:
        self.assertIsNone(convert_value_to_typed("", "integer"))
        self.assertEqual(convert_value_to_typed("abc", "integer"), "abc")
        self.assertEqual(convert_value_to_typed("zzz", "float"), "zzz")
        self.assertEqual(convert_value_to_typed("{bad", "json"), "{bad")

    def test_process_dataset_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            process_dataset(Path("no_such_input_file.csv"))

    def test_process_dataset_empty_csv_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "empty.csv"
            csv_path.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                process_dataset(csv_path)

    def test_sample_size_limits_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "data.csv"
            lines = ["num"] + [str(i) for i in range(4)]
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            schema = process_dataset(csv_path, sample_size=2)
            self.assertEqual(schema["total_rows_analyzed"], 2)


class TestConvertedOutput(unittest.TestCase):
    """Typed CSV export behaviour."""

    def test_conversion_roundtrip_and_blank_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "in.csv"
            csv_path.write_text(
                "num,label\n1,x\nabc,2\n\n",
                encoding="utf-8",
            )
            converted = Path(tmp) / "out.csv"
            process_dataset(csv_path, converted_output=converted)
            rows = list(csv.reader(converted.open(encoding="utf-8")))
            self.assertEqual(rows[0], ["num", "label"])
            self.assertEqual(rows[1], ["1", "x"])
            # Non-numeric value under an integer column stays verbatim.
            self.assertEqual(rows[2], ["abc", "2"])
            # Trailing blank line produced no phantom row.
            self.assertEqual(len(rows), 3)


class TestCliMain(unittest.TestCase):
    """CLI entrypoint behaviour."""

    def _make_csv(self, tmp: str) -> Path:
        csv_path = Path(tmp) / "in.csv"
        csv_path.write_text("num\n1\n2\n", encoding="utf-8")
        return csv_path

    def test_main_success_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = self._make_csv(tmp)
            schema_out = Path(tmp) / "schema.json"
            converted_out = Path(tmp) / "typed.csv"
            rc = main(
                [
                    "-i",
                    str(csv_path),
                    "-s",
                    str(schema_out),
                    "-c",
                    str(converted_out),
                ]
            )
            self.assertEqual(rc, 0)
            schema = json.loads(schema_out.read_text(encoding="utf-8"))
            self.assertEqual(schema["columns"][0]["inferred_type"], "integer")
            self.assertTrue(converted_out.exists())

    def test_main_missing_input_returns_one(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            rc = main(["-i", "no_such_file.csv"])
        self.assertEqual(rc, 1)
        self.assertIn("Error:", err.getvalue())

    def test_module_main_guard_runs_cli(self) -> None:
        script = Path(__file__).resolve().parent.parent / "main.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--input-file", result.stdout)


if __name__ == "__main__":
    unittest.main()

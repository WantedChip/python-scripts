import json
import tempfile
import unittest
from pathlib import Path

from main import (
    analyze_column,
    convert_value_to_typed,
    infer_single_value_type,
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


if __name__ == "__main__":
    unittest.main()

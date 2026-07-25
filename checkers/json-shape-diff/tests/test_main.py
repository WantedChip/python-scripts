"""Unit tests for json-shape-diff main.py."""

import json
import tempfile
import unittest
from pathlib import Path

from main import diff_shapes, extract_shape, is_path_ignored, main, merge_shapes


class TestJsonShapeDiff(unittest.TestCase):
    """Test suite for json-shape-diff tools."""

    def test_extract_primitive_shapes(self) -> None:
        """Test schema shape extraction for basic primitives."""
        self.assertEqual(extract_shape(10)["type"], "number")
        self.assertEqual(extract_shape(10, strict_numbers=True)["type"], "int")
        self.assertEqual(extract_shape("hello")["type"], "str")
        self.assertEqual(extract_shape(True)["type"], "bool")
        self.assertEqual(extract_shape(None)["type"], "null")

    def test_extract_dict_and_list_shapes(self) -> None:
        """Test extracting shape from nested objects and lists."""
        data = {
            "id": 1,
            "name": "Alice",
            "tags": ["admin", "user"],
            "meta": {"active": True},
        }
        shape = extract_shape(data)
        self.assertEqual(shape["type"], "dict")
        props = shape["properties"]
        self.assertEqual(props["id"]["type"], "number")
        self.assertEqual(props["tags"]["type"], "list")
        self.assertEqual(props["tags"]["element_shape"]["type"], "str")

    def test_merge_shapes(self) -> None:
        """Test merging shapes for polymorphic list elements."""
        s1 = {
            "type": "dict",
            "nullable": False,
            "properties": {"a": {"type": "number", "nullable": False}},
        }
        s2 = {
            "type": "dict",
            "nullable": False,
            "properties": {"b": {"type": "str", "nullable": False}},
        }

        merged = merge_shapes(s1, s2)
        props = merged["properties"]
        self.assertTrue(props["a"]["nullable"])
        self.assertTrue(props["b"]["nullable"])

    def test_diff_shapes_missing_and_added(self) -> None:
        """Test detecting added and missing dictionary fields."""
        data_a = {"id": 1, "old_field": "val"}
        data_b = {"id": 2, "new_field": 100}

        shape_a = extract_shape(data_a)
        shape_b = extract_shape(data_b)

        diffs = diff_shapes(shape_a, shape_b)
        diff_types = [d["diff_type"] for d in diffs]

        self.assertIn("MISSING_FIELD", diff_types)
        self.assertIn("ADDED_FIELD", diff_types)

    def test_diff_shapes_type_mismatch(self) -> None:
        """Test type mismatch detection."""
        data_a = {"user_id": 12345}
        data_b = {"user_id": "12345"}

        shape_a = extract_shape(data_a)
        shape_b = extract_shape(data_b)

        diffs = diff_shapes(shape_a, shape_b)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["diff_type"], "TYPE_MISMATCH")

    def test_path_ignoring(self) -> None:
        """Test matching glob ignore patterns."""
        self.assertTrue(is_path_ignored("$.metadata.timestamp", ["$.metadata.*"]))
        self.assertFalse(is_path_ignored("$.user.id", ["$.metadata.*"]))

    def test_main_cli(self) -> None:
        """Test running main CLI with temporary json files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_a = Path(tmp_dir) / "a.json"
            file_b = Path(tmp_dir) / "b.json"
            out_report = Path(tmp_dir) / "report.txt"

            file_a.write_text(json.dumps({"a": 1, "b": "text"}), encoding="utf-8")
            file_b.write_text(json.dumps({"a": 1, "b": 999}), encoding="utf-8")

            ret = main([str(file_a), str(file_b), "-o", str(out_report)])
            self.assertEqual(ret, 2)  # Return code 2 indicates structural diffs found
            self.assertTrue(out_report.exists())
            report_text = out_report.read_text(encoding="utf-8")
            self.assertIn("TYPE_MISMATCH", report_text)


if __name__ == "__main__":
    unittest.main()

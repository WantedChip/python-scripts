"""
Unit tests for JSON flatten nested tool.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from main import export_to_csv, flatten_dict


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


if __name__ == "__main__":
    unittest.main()

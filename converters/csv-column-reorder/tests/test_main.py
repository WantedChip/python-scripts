"""
Unit tests for CSV column reorder tool.
"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from main import inspect_headers, load_config, process_csv


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


if __name__ == "__main__":
    unittest.main()

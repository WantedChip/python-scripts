import csv
import json
import tempfile
import unittest
from pathlib import Path

from main import flatten_json_object, json_to_csv


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


if __name__ == "__main__":
    unittest.main()

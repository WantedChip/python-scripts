import csv
import tempfile
import unittest
from pathlib import Path

from main import merge_csvs, resolve_input_files


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


if __name__ == "__main__":
    unittest.main()

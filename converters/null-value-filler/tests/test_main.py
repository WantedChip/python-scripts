import csv
import tempfile
import unittest
from pathlib import Path

from main import fill_null_values


class TestNullValueFiller(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.input_file = Path(self.temp_dir.name) / "test_input.csv"
        self.output_file = Path(self.temp_dir.name) / "test_output.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_csv(self, data):
        with open(self.input_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(data)

    def _read_csv(self):
        with open(self.output_file, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            return list(reader)

    def test_constant_fill(self):
        data = [
            ["id", "val"],
            ["1", "foo"],
            ["2", "N/A"],
            ["3", ""],
        ]
        self._write_csv(data)
        fill_null_values(
            self.input_file,
            self.output_file,
            strategy="constant",
            constant_value="DEFAULT",
        )
        result = self._read_csv()
        self.assertEqual(result[2][1], "DEFAULT")
        self.assertEqual(result[3][1], "DEFAULT")

    def test_mean_fill(self):
        data = [
            ["id", "val"],
            ["1", "10"],
            ["2", "20"],
            ["3", "null"],
        ]
        self._write_csv(data)
        fill_null_values(
            self.input_file,
            self.output_file,
            strategy="mean",
            columns=["val"],
        )
        result = self._read_csv()
        self.assertEqual(result[3][1], "15")

    def test_median_fill(self):
        data = [
            ["id", "val"],
            ["1", "10"],
            ["2", "20"],
            ["3", "100"],
            ["4", ""],
        ]
        self._write_csv(data)
        fill_null_values(
            self.input_file,
            self.output_file,
            strategy="median",
            columns=["val"],
        )
        result = self._read_csv()
        self.assertEqual(result[4][1], "20")

    def test_mode_fill(self):
        data = [
            ["id", "val"],
            ["1", "apple"],
            ["2", "banana"],
            ["3", "apple"],
            ["4", "NA"],
        ]
        self._write_csv(data)
        fill_null_values(
            self.input_file,
            self.output_file,
            strategy="mode",
            columns=["val"],
        )
        result = self._read_csv()
        self.assertEqual(result[4][1], "apple")

    def test_ffill(self):
        data = [
            ["id", "val"],
            ["1", "first"],
            ["2", "N/A"],
            ["3", "N/A"],
            ["4", "second"],
        ]
        self._write_csv(data)
        fill_null_values(self.input_file, self.output_file, strategy="ffill")
        result = self._read_csv()
        self.assertEqual(result[2][1], "first")
        self.assertEqual(result[3][1], "first")
        self.assertEqual(result[4][1], "second")

    def test_bfill(self):
        data = [
            ["id", "val"],
            ["1", "first"],
            ["2", "N/A"],
            ["3", "second"],
        ]
        self._write_csv(data)
        fill_null_values(self.input_file, self.output_file, strategy="bfill")
        result = self._read_csv()
        self.assertEqual(result[2][1], "second")


if __name__ == "__main__":
    unittest.main()

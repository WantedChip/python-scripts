"""
Unit tests for date format standardizer tool.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from main import parse_date_string, standardize_csv_dates


class TestDateFormatStandardizer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.input_csv = Path(self.temp_dir.name) / "input.csv"
        self.output_csv = Path(self.temp_dir.name) / "output.csv"

        with open(self.input_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "created_at", "updated_at"])
            writer.writerow(["1", "01/15/2024", "Jan 16 2024"])
            writer.writerow(["2", "2024-02-20", "20th March 2024"])
            writer.writerow(["3", "15/03/2024", "invalid_date_string"])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_date_string_varied_formats(self):
        self.assertEqual(parse_date_string("01/15/2024"), "2024-01-15")
        self.assertEqual(parse_date_string("Jan 16 2024"), "2024-01-16")
        self.assertEqual(parse_date_string("2024-02-20"), "2024-02-20")
        self.assertEqual(parse_date_string("20th March 2024"), "2024-03-20")

    def test_parse_date_string_day_first(self):
        # 05/04/2024 could be May 4 (US) or April 5 (EU)
        self.assertEqual(parse_date_string("05/04/2024", day_first=False), "2024-05-04")
        self.assertEqual(parse_date_string("05/04/2024", day_first=True), "2024-04-05")

    def test_parse_date_string_invalid(self):
        self.assertIsNone(parse_date_string("not_a_date"))
        self.assertIsNone(parse_date_string(""))

    def test_standardize_csv_dates_keep_fallback(self):
        stats = standardize_csv_dates(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            target_columns=["created_at", "updated_at"],
            fallback_strategy="keep",
        )

        self.assertEqual(stats["total_rows"], 3)
        self.assertEqual(stats["failed_parses"], 1)

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(rows[0]["created_at"], "2024-01-15")
            self.assertEqual(rows[0]["updated_at"], "2024-01-16")
            self.assertEqual(rows[1]["updated_at"], "2024-03-20")
            # Unparseable fallback keep check
            self.assertEqual(rows[2]["updated_at"], "invalid_date_string")

    def test_standardize_csv_dates_null_fallback(self):
        standardize_csv_dates(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            target_columns=["updated_at"],
            fallback_strategy="null",
        )

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(rows[2]["updated_at"], "")


if __name__ == "__main__":
    unittest.main()

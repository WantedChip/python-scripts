"""
Unit tests for CSV deduplicate rows tool.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from main import deduplicate_csv, is_fuzzy_match


class TestCsvDeduplicateRows(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.input_csv = Path(self.temp_dir.name) / "input.csv"
        self.output_csv = Path(self.temp_dir.name) / "output.csv"

        with open(self.input_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "email", "name", "score"])
            writer.writerow(["1", "user@example.com", "Alice Smith", "100"])
            writer.writerow(["2", "USER@EXAMPLE.COM", "Alice S.", "105"])
            writer.writerow(["3", "bob@example.com", "Bob Jones", "90"])
            writer.writerow(["4", "user@example.com", "Alice Duplicate", "110"])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_deduplicate_keep_first(self):
        stats = deduplicate_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            key_cols=["email"],
            keep="first",
            ignore_case=False,
        )

        self.assertEqual(stats["total_rows"], 4)
        self.assertEqual(stats["retained_rows"], 3)
        self.assertEqual(stats["removed_rows"], 1)

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            emails = [r["email"] for r in rows]
            self.assertIn("user@example.com", emails)
            self.assertIn("USER@EXAMPLE.COM", emails)
            self.assertIn("bob@example.com", emails)

    def test_deduplicate_ignore_case(self):
        stats = deduplicate_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            key_cols=["email"],
            keep="first",
            ignore_case=True,
        )

        self.assertEqual(stats["retained_rows"], 2)
        self.assertEqual(stats["removed_rows"], 2)

    def test_deduplicate_keep_last(self):
        stats = deduplicate_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            key_cols=["email"],
            keep="last",
            ignore_case=False,
        )
        self.assertEqual(stats["retained_rows"], 3)

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # Row id 4 should be retained instead of row id 1 for user@example.com
            retained_ids = [r["id"] for r in rows]
            self.assertIn("4", retained_ids)
            self.assertNotIn("1", retained_ids)

    def test_fuzzy_match(self):
        seen = ["Alice Smith"]
        self.assertTrue(is_fuzzy_match("Alice Smith", seen, threshold=0.8))
        self.assertTrue(is_fuzzy_match("Alice Smyth", seen, threshold=0.8))
        self.assertFalse(is_fuzzy_match("Bob Jones", seen, threshold=0.8))

    def test_fuzzy_deduplication(self):
        stats = deduplicate_csv(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            key_cols=["name"],
            keep="first",
            fuzzy_threshold=0.7,
        )
        self.assertLess(stats["retained_rows"], stats["total_rows"])


if __name__ == "__main__":
    unittest.main()

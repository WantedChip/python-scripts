import csv
import tempfile
import unittest
from pathlib import Path

from main import clean_cell_whitespace, clean_text_content, clean_whitespace


class TestWhitespaceCleaner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.txt_file = self.dir_path / "sample.txt"
        self.csv_file = self.dir_path / "sample.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_clean_cell_whitespace(self):
        self.assertEqual(clean_cell_whitespace("   hello    world   "), "hello world")
        self.assertEqual(
            clean_cell_whitespace("  col1\tcol2  ", convert_tabs=True, tab_width=4),
            "col1 col2",
        )
        self.assertEqual(
            clean_cell_whitespace("   keep   spaces   ", collapse_internal=False),
            "keep   spaces",
        )

    def test_clean_text_content(self):
        content = "  line 1   \r\n\r\n  line  2  \t  with tabs  "
        cleaned = clean_text_content(content, convert_tabs=True)
        expected = "line 1\n\nline 2 with tabs"
        self.assertEqual(cleaned, expected)

    def test_clean_csv_in_place(self):
        csv_data = [
            ["  name ", "  age  ", "  city  "],
            [" Alice ", "  30  ", " New   York "],
        ]
        with open(self.csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)

        clean_whitespace(self.csv_file, in_place=True)

        with open(self.csv_file, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))

        self.assertEqual(rows[0], ["name", "age", "city"])
        expected_row1 = ["Alice", "30", "New York"]
        self.assertEqual(rows[1], expected_row1)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for csv-forensics main.py."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from main import (
    analyze_csv,
    check_excel_corruption,
    check_headers,
    check_invisible_and_control_chars,
    detect_encoding_and_bom,
    main,
)


class TestCsvForensics(unittest.TestCase):
    """Test suite for csv-forensics tool."""

    def test_detect_encoding_and_bom(self) -> None:
        """Test detecting UTF-8 BOM byte sequence."""
        content = b"\xef\xbb\xbfid,name\n1,Alice\n"
        encoding, bom, issues = detect_encoding_and_bom(content)
        self.assertEqual(bom, "UTF-8-BOM")
        self.assertEqual(encoding, "utf-8-sig")
        self.assertEqual(len(issues), 1)

    def test_check_invisible_chars(self) -> None:
        """Test identifying zero-width spaces and control characters."""
        text = "header_id,name\n1,\u200bAlice\n2,Bob\x01\n"
        issues = check_invisible_and_control_chars(text)
        self.assertEqual(len(issues), 2)
        categories = [i.category for i in issues]
        self.assertIn("CONTROL_CHARS", categories)

    def test_check_headers(self) -> None:
        """Test detecting duplicate or empty headers."""
        headers = ["id", "Name ", "", "id"]
        issues = check_headers(headers)
        messages = [i.message for i in issues]
        self.assertTrue(any("whitespace" in m for m in messages))
        self.assertTrue(any("Empty header" in m for m in messages))
        self.assertTrue(any("Duplicate header" in m for m in messages))

    def test_excel_corruption(self) -> None:
        """Test detecting Excel scientific notation and formula errors."""
        headers = ["user_id", "status"]
        rows = [
            ["1.23E+11", "#VALUE!"],
            ["99999", "OK"],
        ]
        issues = check_excel_corruption(headers, rows)
        categories = [i.category for i in issues]
        self.assertIn("EXCEL_CORRUPTION", categories)

    def test_analyze_csv(self) -> None:
        """Test full forensic analysis on a CSV file with row mismatches."""
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp:
            tmp.write("id,name,role\n1,Alice\n2,Bob,admin,extra_col\n")
            tmp_path = tmp.name

        try:
            report = analyze_csv(Path(tmp_path))
            summary = report["summary"]
            self.assertEqual(summary["header_count"], 3)
            self.assertEqual(summary["total_data_rows"], 2)
            issues = report["issues"]
            self.assertTrue(any(i["category"] == "ROW_MALFORMED" for i in issues))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_main_cli(self) -> None:
        """Test running main CLI on temporary CSV file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "test.csv"
            out_report = Path(tmp_dir) / "report.json"

            csv_path.write_text("col_a,col_b\n1,val1\n2,val2\n", encoding="utf-8")

            ret = main([str(csv_path), "-f", "json", "-o", str(out_report)])
            self.assertEqual(ret, 0)
            self.assertTrue(out_report.exists())
            data = json.loads(out_report.read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["total_data_rows"], 2)


if __name__ == "__main__":
    unittest.main()

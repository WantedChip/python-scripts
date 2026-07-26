import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from main import (
    export_csv_report,
    export_json_report,
    find_duplicates,
    process_deletion,
    process_quarantine,
)


class TestDuplicateFileFinder(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_find_duplicates(self):
        content_a = b"Exact duplicate content for testing."
        content_b = b"Different content altogether."

        f1 = self.test_dir / "file1.txt"
        f2 = self.test_dir / "sub" / "file2.txt"
        f3 = self.test_dir / "unique.txt"

        f2.parent.mkdir(parents=True, exist_ok=True)

        f1.write_bytes(content_a)
        f2.write_bytes(content_a)
        f3.write_bytes(content_b)

        groups = find_duplicates(self.test_dir)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].files), 2)
        self.assertEqual(groups[0].file_size, len(content_a))

    def test_export_json_and_csv(self):
        f1 = self.test_dir / "a.txt"
        f2 = self.test_dir / "b.txt"
        f1.write_text("duplicate text")
        f2.write_text("duplicate text")

        groups = find_duplicates(self.test_dir)

        json_file = self.test_dir / "report.json"
        csv_file = self.test_dir / "report.csv"

        export_json_report(groups, json_file)
        export_csv_report(groups, csv_file)

        self.assertTrue(json_file.exists())
        with open(json_file, "r") as f:
            data = json.load(f)
            self.assertEqual(data["summary"]["group_count"], 1)

        self.assertTrue(csv_file.exists())
        with open(csv_file, "r") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 3)  # Header + original + duplicate

    def test_quarantine_duplicates(self):
        f1 = self.test_dir / "orig.bin"
        f2 = self.test_dir / "copy.bin"
        f1.write_bytes(b"1234567890")
        f2.write_bytes(b"1234567890")

        groups = find_duplicates(self.test_dir)
        q_dir = self.test_dir / "quarantine"

        moved = process_quarantine(groups, q_dir, dry_run=False)
        self.assertEqual(len(moved), 1)
        self.assertTrue(f1.exists())
        self.assertFalse(f2.exists())
        self.assertTrue((q_dir / "copy.bin").exists())

    def test_delete_duplicates(self):
        f1 = self.test_dir / "orig.bin"
        f2 = self.test_dir / "copy.bin"
        f1.write_bytes(b"1234567890")
        f2.write_bytes(b"1234567890")

        groups = find_duplicates(self.test_dir)
        deleted = process_deletion(groups, dry_run=False)

        self.assertEqual(len(deleted), 1)
        self.assertTrue(f1.exists())
        self.assertFalse(f2.exists())


if __name__ == "__main__":
    unittest.main()

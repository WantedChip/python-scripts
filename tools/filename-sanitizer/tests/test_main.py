"""Unit tests for filename-sanitizer."""

import shutil
import tempfile
import unittest
from pathlib import Path

from main import remove_diacritics, sanitize_directory, sanitize_filename


class TestFilenameSanitizer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.target_dir = Path(self.temp_dir) / "files"
        self.target_dir.mkdir()

        self.file1 = self.target_dir / "Crème Brûlée 2023!.txt"
        self.file1.write_text("test", encoding="utf-8")

        self.file2 = self.target_dir / "bad:name<test>?.pdf"
        self.file2.write_text("test", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_remove_diacritics(self):
        self.assertEqual(remove_diacritics("Crème Brûlée"), "Creme Brulee")

    def test_sanitize_filename_windows(self):
        cleaned = sanitize_filename("bad:name<test>?.pdf", target_os="windows")
        self.assertEqual(cleaned, "badnametest.pdf")

    def test_sanitize_filename_options(self):
        cleaned = sanitize_filename(
            "Crème Brûlée.txt", space_replacement="-", lowercase=True
        )
        self.assertEqual(cleaned, "creme-brulee.txt")

    def test_sanitize_directory_dry_run(self):
        diffs = sanitize_directory(self.target_dir, dry_run=True)
        self.assertEqual(len(diffs), 2)
        self.assertTrue(self.file1.exists())

    def test_sanitize_directory_execute(self):
        diffs = sanitize_directory(self.target_dir, dry_run=False)
        self.assertEqual(len(diffs), 2)
        self.assertFalse(self.file1.exists())
        renamed_files = [f.name for f in self.target_dir.iterdir()]
        self.assertIn("Creme_Brulee_2023.txt", renamed_files)
        self.assertIn("badnametest.pdf", renamed_files)


if __name__ == "__main__":
    unittest.main()

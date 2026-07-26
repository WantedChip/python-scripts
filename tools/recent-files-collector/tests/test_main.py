"""Unit tests for recent-files-collector."""

import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from main import collect_recent_files, generate_unique_filename, is_file_recent


class TestRecentFilesCollector(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "source"
        self.dest_dir = Path(self.temp_dir) / "dest"
        self.source_dir.mkdir()

        # Create test files
        self.file1 = self.source_dir / "doc1.txt"
        self.file1.write_text("Hello World", encoding="utf-8")

        self.sub_dir = self.source_dir / "sub"
        self.sub_dir.mkdir()
        self.file2 = self.sub_dir / "doc2.pdf"
        self.file2.write_text("PDF Content", encoding="utf-8")

        self.file_dup = self.sub_dir / "doc1.txt"
        self.file_dup.write_text("Duplicate Doc1", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_is_file_recent(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(is_file_recent(self.file1, days=1.0, now=now))
        future_dt = now + timedelta(days=2)
        self.assertFalse(is_file_recent(self.file1, days=0.0, now=future_dt))

    def test_generate_unique_filename(self):
        used: set[str] = set()
        name1 = generate_unique_filename(
            self.dest_dir, "doc.txt", used, self.file1, strategy="counter"
        )
        self.assertEqual(name1, "doc.txt")

        name2 = generate_unique_filename(
            self.dest_dir, "doc.txt", used, self.file2, strategy="counter"
        )
        self.assertEqual(name2, "doc_1.txt")

        name_hash = generate_unique_filename(
            self.dest_dir, "doc.txt", used, self.file2, strategy="hash"
        )
        self.assertTrue(name_hash.startswith("doc_") and name_hash.endswith(".txt"))

    def test_collect_recent_files(self):
        manifest = collect_recent_files(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            days=1.0,
            collision_strategy="counter",
        )
        self.assertEqual(len(manifest), 3)
        self.assertTrue(self.dest_dir.exists())
        copied_files = [f.name for f in self.dest_dir.iterdir()]
        self.assertIn("doc1.txt", copied_files)
        self.assertIn("doc1_1.txt", copied_files)
        self.assertIn("doc2.pdf", copied_files)

    def test_collect_with_extension_filter(self):
        manifest = collect_recent_files(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            days=1.0,
            extensions=[".pdf"],
        )
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["filename"], "doc2.pdf")

    def test_dry_run(self):
        manifest = collect_recent_files(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            days=1.0,
            dry_run=True,
        )
        self.assertEqual(len(manifest), 3)
        self.assertFalse(self.dest_dir.exists())


if __name__ == "__main__":
    unittest.main()

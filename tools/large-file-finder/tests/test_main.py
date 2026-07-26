"""Unit tests for large-file-finder."""

import shutil
import tempfile
import unittest
from pathlib import Path

from main import format_bytes, parse_size_string, scan_large_files


class TestLargeFileFinder(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.scan_dir = Path(self.temp_dir) / "data"
        self.scan_dir.mkdir()

        # Create files of varying sizes
        self.small_file = self.scan_dir / "small.txt"
        self.small_file.write_bytes(b"A" * 500)  # 500 B

        self.large_file = self.scan_dir / "large.bin"
        self.large_file.write_bytes(b"B" * (2 * 1024 * 1024))  # 2 MB

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_parse_size_string(self):
        self.assertEqual(parse_size_string("100"), 100)
        self.assertEqual(parse_size_string("1KB"), 1024)
        self.assertEqual(parse_size_string("10MB"), 10 * 1024 * 1024)
        self.assertEqual(parse_size_string("1.5GB"), int(1.5 * 1024 * 1024 * 1024))

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500 B")
        self.assertEqual(format_bytes(1024 * 1024), "1.00 MB")

    def test_scan_large_files(self):
        files, summary = scan_large_files(self.scan_dir, min_size_bytes=1 * 1024 * 1024)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["filename"], "large.bin")
        self.assertIn(".bin", summary)
        self.assertEqual(summary[".bin"]["count"], 1)

    def test_scan_top_n(self):
        # Create another large file
        another_large = self.scan_dir / "huge.dat"
        another_large.write_bytes(b"C" * (5 * 1024 * 1024))

        files, _ = scan_large_files(self.scan_dir, min_size_bytes=1, top_n=1)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["filename"], "huge.dat")


if __name__ == "__main__":
    unittest.main()

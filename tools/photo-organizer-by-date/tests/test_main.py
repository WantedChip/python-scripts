"""Unit tests for photo-organizer-by-date."""

import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from main import format_subfolder_path, get_photo_date, organize_photos


class TestPhotoOrganizer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "photos"
        self.dest_dir = Path(self.temp_dir) / "organized"
        self.source_dir.mkdir()

        # Create dummy image file
        self.img1 = self.source_dir / "photo1.jpg"
        header = (
            b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60"
            b"\x00\x00\xFF\xD9"
        )
        self.img1.write_bytes(header)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_format_subfolder_path(self):
        dt = datetime(2023, 5, 17, 14, 30, 0)
        self.assertEqual(format_subfolder_path(dt, "YYYY/MM"), Path("2023/05"))
        self.assertEqual(format_subfolder_path(dt, "YYYY-MM-DD"), Path("2023-05-17"))
        self.assertEqual(format_subfolder_path(dt, "YYYY/MM/DD"), Path("2023/05/17"))

    def test_get_photo_date_fallback(self):
        dt = get_photo_date(self.img1)
        self.assertIsInstance(dt, datetime)

    def test_organize_photos_copy(self):
        results = organize_photos(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            folder_format="YYYY/MM",
            mode="copy",
        )
        self.assertEqual(len(results), 1)
        self.assertTrue(self.img1.exists())  # Source remains in copy mode
        dest_files = list(self.dest_dir.rglob("*.jpg"))
        self.assertEqual(len(dest_files), 1)

    def test_organize_photos_move(self):
        results = organize_photos(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            folder_format="YYYY-MM-DD",
            mode="move",
        )
        self.assertEqual(len(results), 1)
        self.assertFalse(self.img1.exists())  # Source moved
        dest_files = list(self.dest_dir.rglob("*.jpg"))
        self.assertEqual(len(dest_files), 1)


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for Filename Case Normalizer.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from main import (
    convert_filename,
    process_directory,
    resolve_collision,
    to_snake_case,
    undo_renames,
)


class TestFilenameCaseNormalizer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_to_snake_case(self):
        self.assertEqual(to_snake_case("myCamelCaseFile"), "my_camel_case_file")
        self.assertEqual(to_snake_case("hello world-file"), "hello_world_file")
        self.assertEqual(to_snake_case("SimpleTest123"), "simple_test123")

    def test_convert_filename(self):
        self.assertEqual(convert_filename("MyFile.TXT", "lowercase"), "myfile.txt")
        self.assertEqual(convert_filename("myfile.txt", "uppercase"), "MYFILE.txt")
        self.assertEqual(
            convert_filename("my_file_name.txt", "title"), "My_File_Name.txt"
        )
        self.assertEqual(
            convert_filename("my cool File.png", "snake"), "my_cool_file.png"
        )

    def test_resolve_collision_append_number(self):
        file1 = self.temp_dir / "test.txt"
        file1.touch()

        target = self.temp_dir / "test.txt"
        resolved = resolve_collision(target, set(), strategy="append_number")
        self.assertEqual(resolved.name, "test_1.txt")

    def test_process_directory_dry_run(self):
        f = self.temp_dir / "TestFile.txt"
        f.touch()

        renames = process_directory(self.temp_dir, mode="lowercase", dry_run=True)
        self.assertEqual(len(renames), 1)
        self.assertTrue(f.exists())  # Still original name in dry-run

    def test_process_directory_and_undo(self):
        f = self.temp_dir / "TestFile.txt"
        f.touch()

        manifest = self.temp_dir / "manifest.json"
        renames = process_directory(
            self.temp_dir, mode="lowercase", dry_run=False, manifest_path=manifest
        )
        self.assertEqual(len(renames), 1)
        self.assertFalse(f.exists())
        renamed_file = self.temp_dir / "testfile.txt"
        self.assertTrue(renamed_file.exists())
        self.assertTrue(manifest.exists())

        # Test Undo
        restored_count = undo_renames(manifest)
        self.assertEqual(restored_count, 1)
        self.assertTrue(f.exists())
        self.assertFalse(renamed_file.exists())


if __name__ == "__main__":
    unittest.main()

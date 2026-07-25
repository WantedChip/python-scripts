import shutil
import tempfile
import unittest
from pathlib import Path

from main import (
    execute_cleaning,
    find_empty_folders,
    is_folder_excluded,
    is_hidden_or_system,
)


class TestEmptyFolderCleaner(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_is_hidden_or_system(self):
        self.assertTrue(is_hidden_or_system(Path(".DS_Store")))
        self.assertTrue(is_hidden_or_system(Path(".hidden_folder")))
        self.assertTrue(is_hidden_or_system(Path("desktop.ini")))
        self.assertFalse(is_hidden_or_system(Path("regular_file.txt")))

    def test_is_folder_excluded(self):
        self.assertTrue(is_folder_excluded(Path(".git"), {".git"}))
        self.assertTrue(is_folder_excluded(Path("node_modules"), {"node_modules"}))
        self.assertFalse(is_folder_excluded(Path("my_folder"), {".git"}))

    def test_find_empty_folders_nested(self):
        # Create nested empty tree: level1/level2/level3
        nested = self.test_dir / "level1" / "level2" / "level3"
        nested.mkdir(parents=True, exist_ok=True)

        # Non-empty branch: non_empty/file.txt
        non_empty = self.test_dir / "non_empty"
        non_empty.mkdir(parents=True, exist_ok=True)
        (non_empty / "file.txt").write_text("data")

        candidates = find_empty_folders(self.test_dir)
        candidate_dirs = [c.directory for c in candidates]

        self.assertIn(self.test_dir / "level1" / "level2" / "level3", candidate_dirs)
        self.assertIn(self.test_dir / "level1" / "level2", candidate_dirs)
        self.assertIn(self.test_dir / "level1", candidate_dirs)
        self.assertNotIn(non_empty, candidate_dirs)

    def test_execute_cleaning(self):
        empty_sub = self.test_dir / "empty_sub"
        empty_sub.mkdir()

        junk_sub = self.test_dir / "junk_sub"
        junk_sub.mkdir()
        (junk_sub / ".DS_Store").touch()

        candidates = find_empty_folders(
            self.test_dir, ignore_hidden_files=True, delete_junk_files=True
        )
        folders_del, files_del = execute_cleaning(candidates, dry_run=False)

        self.assertEqual(folders_del, 2)
        self.assertEqual(files_del, 1)
        self.assertFalse(empty_sub.exists())
        self.assertFalse(junk_sub.exists())

    def test_excluded_folders_ignored(self):
        git_dir = self.test_dir / ".git"
        git_dir.mkdir()

        candidates = find_empty_folders(self.test_dir, exclude_patterns={".git"})
        candidate_dirs = [c.directory for c in candidates]
        self.assertNotIn(git_dir, candidate_dirs)


if __name__ == "__main__":
    unittest.main()

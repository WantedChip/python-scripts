import shutil
import tempfile
import unittest
from pathlib import Path

from main import compute_sha256, sync_folders


class TestFolderSyncTool(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "source"
        self.dest_dir = Path(self.temp_dir) / "dest"
        self.source_dir.mkdir()
        self.dest_dir.mkdir()

        self.file1 = self.source_dir / "doc1.txt"
        self.file1.write_text("Hello World", encoding="utf-8")

        self.file2 = self.dest_dir / "extra.txt"
        self.file2.write_text("Extra file in dest", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_compute_sha256(self):
        h = compute_sha256(self.file1)
        self.assertEqual(len(h), 64)

    def test_sync_one_way(self):
        logs = sync_folders(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            direction="one-way",
            delete=False,
        )
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "copy_new")
        self.assertTrue((self.dest_dir / "doc1.txt").exists())
        self.assertTrue(self.file2.exists())

    def test_sync_one_way_with_delete(self):
        logs = sync_folders(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            direction="one-way",
            delete=True,
        )
        self.assertEqual(len(logs), 2)
        self.assertFalse(self.file2.exists())  # Deleted from dest

    def test_sync_bidirectional(self):
        logs = sync_folders(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            direction="bidirectional",
        )
        self.assertEqual(len(logs), 2)
        self.assertTrue((self.dest_dir / "doc1.txt").exists())
        self.assertTrue((self.source_dir / "extra.txt").exists())


if __name__ == "__main__":
    unittest.main()

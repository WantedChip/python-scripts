"""Unit tests for Backup Rotation Manager."""

import datetime
import os
import tempfile
import unittest
from pathlib import Path

from main import BackupRotationManager, parse_args


class TestBackupRotationManager(unittest.TestCase):
    """Test suite for BackupRotationManager."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_mock_file(self, filename: str, mtime_offset_days: int = 0) -> Path:
        """Create temp backup file with specific modification time."""
        file_path = self.test_dir / filename
        file_path.write_text(f"content of {filename}")

        # Set modification time back by mtime_offset_days
        now = datetime.datetime.now().timestamp()
        target_mtime = now - (mtime_offset_days * 86400)
        os.utime(file_path, (target_mtime, target_mtime))
        return file_path

    def test_list_backups_pattern_and_sort(self) -> None:
        self.create_mock_file("backup_old.tar.gz", mtime_offset_days=5)
        self.create_mock_file("backup_new.tar.gz", mtime_offset_days=1)
        self.create_mock_file("other.txt", mtime_offset_days=0)

        manager = BackupRotationManager(self.test_dir, pattern="*.tar.gz")
        backups = manager.list_backups()

        self.assertEqual(len(backups), 2)
        self.assertEqual(backups[0].path.name, "backup_new.tar.gz")
        self.assertEqual(backups[1].path.name, "backup_old.tar.gz")

    def test_keep_count_retention(self) -> None:
        f1 = self.create_mock_file("b1.db", mtime_offset_days=3)
        f2 = self.create_mock_file("b2.db", mtime_offset_days=2)
        f3 = self.create_mock_file("b3.db", mtime_offset_days=1)

        manager = BackupRotationManager(self.test_dir, pattern="*.db")
        result = manager.execute_rotation(keep_count=2, dry_run=False)

        self.assertEqual(len(result["retained"]), 2)
        self.assertEqual(len(result["purged"]), 1)
        self.assertTrue(f3.exists())
        self.assertTrue(f2.exists())
        self.assertFalse(f1.exists())

    def test_keep_daily_retention(self) -> None:
        # Create 3 files on 3 distinct days
        f1 = self.create_mock_file("b1.tar", mtime_offset_days=10)
        f2 = self.create_mock_file("b2.tar", mtime_offset_days=2)
        f3 = self.create_mock_file("b3.tar", mtime_offset_days=1)

        manager = BackupRotationManager(self.test_dir, pattern="*.tar")
        result = manager.execute_rotation(keep_daily=2, dry_run=False)

        self.assertEqual(len(result["retained"]), 2)
        self.assertTrue(f3.exists())
        self.assertTrue(f2.exists())
        self.assertFalse(f1.exists())

    def test_dry_run_mode(self) -> None:
        f1 = self.create_mock_file("b1.zip", mtime_offset_days=5)
        f2 = self.create_mock_file("b2.zip", mtime_offset_days=1)

        manager = BackupRotationManager(self.test_dir, pattern="*.zip")
        result = manager.execute_rotation(keep_count=1, dry_run=True)

        self.assertEqual(len(result["purged"]), 1)
        # Verify file was NOT actually deleted in dry-run mode
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())

    def test_parse_args(self) -> None:
        args = parse_args(
            ["/tmp/backups", "--pattern", "*.tar", "-k", "5", "--dry-run"]
        )
        self.assertEqual(args.directory, "/tmp/backups")
        self.assertEqual(args.pattern, "*.tar")
        self.assertEqual(args.keep, 5)
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main()

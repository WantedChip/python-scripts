import os
import shutil
import tempfile
import unittest
from pathlib import Path

from main import (
    are_files_identical,
    build_parser,
    compute_sha256,
    main,
    scan_tree,
    sync_folders,
)


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


class TestScanAndCompare(unittest.TestCase):
    """Unit tests for tree scanning and file comparison helpers."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_scan_tree_missing_root_returns_empty(self) -> None:
        """Scanning a nonexistent root yields an empty mapping."""
        self.assertEqual(scan_tree(self.root / "ghost"), {})

    def test_scan_tree_maps_relative_paths(self) -> None:
        """Entries map relative posix paths to size/mtime metadata."""
        sub = self.root / "nested"
        sub.mkdir()
        (sub / "f.txt").write_text("data", encoding="utf-8")

        tree = scan_tree(self.root)
        self.assertIn("nested/f.txt", tree)
        self.assertEqual(tree["nested/f.txt"]["size"], 4.0)

    def test_are_files_identical_by_checksum(self) -> None:
        """Equal content matches even when names and mtimes differ."""
        a = self.root / "a.txt"
        b = self.root / "b.txt"
        a.write_text("same", encoding="utf-8")
        b.write_text("same", encoding="utf-8")
        os.utime(a, (1000, 1000))
        os.utime(b, (2000, 2000))

        self.assertTrue(are_files_identical(a, b))

    def test_are_files_identical_size_mismatch_short_circuits(self) -> None:
        """Different sizes never require hashing."""
        a = self.root / "s1.txt"
        b = self.root / "s2.txt"
        a.write_text("short", encoding="utf-8")
        b.write_text("longer text", encoding="utf-8")

        self.assertFalse(are_files_identical(a, b))

    def test_are_files_identical_same_size_different_content(self) -> None:
        """Same-size files with different bytes compare as different."""
        a = self.root / "c1.txt"
        b = self.root / "c2.txt"
        a.write_text("alpha", encoding="utf-8")
        b.write_text("bravo", encoding="utf-8")

        self.assertFalse(are_files_identical(a, b))

    def test_are_files_identical_mtime_mode(self) -> None:
        """Without checksums, close mtimes count as identical."""
        a = self.root / "m1.txt"
        b = self.root / "m2.txt"
        a.write_text("same-size!!", encoding="utf-8")
        b.write_text("other-size!", encoding="utf-8")
        os.utime(a, (500000, 500000))
        os.utime(b, (500000.5, 500000.5))

        # Different content would fail the checksum path, proving mtimes
        # alone drive this comparison mode.
        self.assertFalse(are_files_identical(a, b))
        self.assertTrue(are_files_identical(a, b, use_checksum=False))


class TestSyncDirections(unittest.TestCase):
    """Behaviour tests for one-way updates and bidirectional merging."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "src"
        self.dest_dir = Path(self.temp_dir) / "dst"
        self.source_dir.mkdir()
        self.dest_dir.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _write(self, base: Path, name: str, content: str) -> Path:
        """Write a helper file under the given root."""
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_one_way_updates_changed_files(self) -> None:
        """Files present on both sides with new content are updated."""
        src_file = self._write(self.source_dir, "doc.txt", "version 1")
        dst_file = self._write(self.dest_dir, "doc.txt", "stale")
        os.utime(src_file, (2000, 2000))
        os.utime(dst_file, (1000, 1000))

        logs = sync_folders(self.source_dir, self.dest_dir, "one-way")

        self.assertEqual([log["action"] for log in logs], ["update"])
        self.assertEqual(dst_file.read_text(encoding="utf-8"), "version 1")

    def test_one_way_dry_run_writes_nothing(self) -> None:
        """Dry-run reports actions but leaves both trees untouched."""
        self._write(self.source_dir, "new.txt", "fresh")
        missing_dest = self.dest_dir / "missing"

        logs = sync_folders(self.source_dir, self.dest_dir, "one-way", dry_run=True)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "copy_new")
        self.assertFalse(missing_dest.exists())

    def test_bidirectional_conflict_keeps_copy(self) -> None:
        """Simultaneous edits produce a .conflict copy in destination."""
        src_file = self._write(self.source_dir, "shared.txt", "from source")
        dst_file = self._write(self.dest_dir, "shared.txt", "from dest")
        os.utime(src_file, (1500, 1500))
        os.utime(dst_file, (1500.2, 1500.2))

        logs = sync_folders(self.source_dir, self.dest_dir, "bidirectional")

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "conflict")
        conflict_file = self.dest_dir / "shared.txt.conflict"
        self.assertTrue(conflict_file.exists())
        self.assertEqual(conflict_file.read_text(encoding="utf-8"), "from source")
        # Both originals keep their divergent content.
        self.assertEqual(src_file.read_text(encoding="utf-8"), "from source")
        self.assertEqual(dst_file.read_text(encoding="utf-8"), "from dest")

    def test_bidirectional_source_newer_updates_dest(self) -> None:
        """A newer source overwrites the stale destination copy."""
        src_file = self._write(self.source_dir, "report.txt", "source wins")
        dst_file = self._write(self.dest_dir, "report.txt", "dest old")
        os.utime(src_file, (3000, 3000))
        os.utime(dst_file, (2000, 2000))

        logs = sync_folders(self.source_dir, self.dest_dir, "bidirectional")

        self.assertEqual([log["action"] for log in logs], ["update_dest"])
        self.assertEqual(dst_file.read_text(encoding="utf-8"), "source wins")

    def test_bidirectional_dest_newer_updates_source(self) -> None:
        """A newer destination propagates back into the source."""
        src_file = self._write(self.source_dir, "notes.txt", "src old")
        dst_file = self._write(self.dest_dir, "notes.txt", "dest wins")
        os.utime(src_file, (1000, 1000))
        os.utime(dst_file, (4000, 4000))

        logs = sync_folders(self.source_dir, self.dest_dir, "bidirectional")

        self.assertEqual([log["action"] for log in logs], ["update_source"])
        self.assertEqual(src_file.read_text(encoding="utf-8"), "dest wins")


class TestMainCLI(unittest.TestCase):
    """CLI entry point tests."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "src"
        self.dest_dir = Path(self.temp_dir) / "dst"
        self.source_dir.mkdir()
        (self.source_dir / "f.txt").write_text("x", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_main_syncs_and_writes_log(self) -> None:
        """The CLI syncs folders and persists the JSON execution log."""
        log_path = Path(self.temp_dir) / "log.json"

        code = main(
            [
                "--source",
                str(self.source_dir),
                "--dest",
                str(self.dest_dir),
                "--log-file",
                str(log_path),
            ]
        )

        self.assertEqual(code, 0)
        self.assertTrue((self.dest_dir / "f.txt").exists())
        self.assertTrue(log_path.exists())
        self.assertIn("copy_new", log_path.read_text(encoding="utf-8"))

    def test_main_dry_run_flag(self) -> None:
        """--dry-run proposes actions without touching the filesystem."""
        log_path = Path(self.temp_dir) / "dry.json"
        code = main(
            [
                "--source",
                str(self.source_dir),
                "--dest",
                str(self.dest_dir),
                "--log-file",
                str(log_path),
                "--dry-run",
            ]
        )
        self.assertEqual(code, 0)
        self.assertFalse((self.dest_dir / "f.txt").exists())
        self.assertIn("copy_new", log_path.read_text(encoding="utf-8"))

    def test_build_parser_defaults(self) -> None:
        """Parser defaults to one-way sync with checksums enabled."""
        parsed = build_parser().parse_args(["-s", "a", "-d", "b"])
        self.assertEqual(parsed.direction, "one-way")
        self.assertFalse(parsed.delete)
        self.assertTrue(parsed.checksum)
        self.assertFalse(parsed.dry_run)


if __name__ == "__main__":
    unittest.main()

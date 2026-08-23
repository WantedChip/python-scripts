"""Unit tests for recent-files-collector."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from main import (
    collect_recent_files,
    generate_unique_filename,
    get_file_timestamp,
    is_file_recent,
    main,
)


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


class TestCollectorEdges(unittest.TestCase):
    """Edge branches of timestamping, collisions and collection."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "source"
        self.dest_dir = Path(self.temp_dir) / "dest"
        self.source_dir.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_file_timestamp_ctime_returns_float(self) -> None:
        target = self.source_dir / "a.txt"
        target.write_text("x", encoding="utf-8")
        ts = get_file_timestamp(target, "ctime")
        self.assertIsInstance(ts, float)

    def test_counter_collision_increments_past_existing(self) -> None:
        (self.dest_dir / "").mkdir(parents=True, exist_ok=True)
        (self.dest_dir / "a.txt").write_text("1", encoding="utf-8")
        (self.dest_dir / "a_1.txt").write_text("2", encoding="utf-8")
        src = self.source_dir / "other.txt"
        src.write_text("3", encoding="utf-8")
        name = generate_unique_filename(
            dest_dir=self.dest_dir,
            original_name="a.txt",
            used_names=set(),
            source_path=src,
            strategy="counter",
        )
        self.assertEqual(name, "a_2.txt")

    def test_collect_skips_files_already_inside_dest(self) -> None:
        nested_dest = self.source_dir / "collected"
        nested_dest.mkdir()
        inside = nested_dest / "inner.txt"
        inside.write_text("recent", encoding="utf-8")
        manifest = collect_recent_files(
            source_dir=self.source_dir,
            dest_dir=nested_dest,
            days=7.0,
        )
        self.assertEqual(
            [r["filename"] for r in manifest],
            [],
        )

    def test_collect_skips_paths_failing_stat(self) -> None:
        import main as main_module

        fresh = self.source_dir / "fresh.txt"
        fresh.write_text("data", encoding="utf-8")
        ghost = self.source_dir / "ghost.txt"
        ghost.write_text("vanishing", encoding="utf-8")

        original = main_module.is_file_recent

        def selective(path, days, **kwargs):
            if path.name == "ghost.txt":
                raise OSError("stat failed")
            return original(path, days, **kwargs)

        with mock.patch.object(main_module, "is_file_recent", side_effect=selective):
            manifest = collect_recent_files(
                source_dir=self.source_dir,
                dest_dir=self.dest_dir,
                days=7.0,
            )
        self.assertEqual([r["filename"] for r in manifest], ["fresh.txt"])

    def test_copy_failure_recorded_as_failed(self) -> None:
        fresh = self.source_dir / "fresh.txt"
        fresh.write_text("data", encoding="utf-8")
        with mock.patch.object(
            shutil,
            "copy2",
            side_effect=OSError(13, "permission denied"),
        ):
            manifest = collect_recent_files(
                source_dir=self.source_dir,
                dest_dir=self.dest_dir,
                days=7.0,
            )
        self.assertEqual(len(manifest), 1)
        self.assertTrue(manifest[0]["status"].startswith("failed:"))


class TestCollectorCli(unittest.TestCase):
    """CLI entrypoint behaviour."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "source"
        self.dest_dir = Path(self.temp_dir) / "dest"
        self.source_dir.mkdir()
        (self.source_dir / "new.txt").write_text("body", encoding="utf-8")
        (self.source_dir / "old.log").write_text("stale", encoding="utf-8")
        old = self.source_dir / "old.log"
        stamp = time.time() - 30 * 24 * 3600
        os.utime(old, (stamp, stamp))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_copies_and_writes_manifest(self) -> None:
        manifest_path = Path(self.temp_dir) / "manifest.json"
        rc = main(
            [
                "--source",
                str(self.source_dir),
                "--dest",
                str(self.dest_dir),
                "--extensions",
                ".txt",
                "--manifest",
                str(manifest_path),
            ]
        )
        self.assertEqual(rc, 0)
        self.assertTrue((self.dest_dir / "new.txt").exists())
        self.assertFalse((self.dest_dir / "old.log").exists())
        records = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(records[0]["status"], "copied")

    def test_cli_dry_run_copies_nothing(self) -> None:
        rc = main(
            [
                "--source",
                str(self.source_dir),
                "--dest",
                str(self.dest_dir),
                "--dry-run",
                "--manifest",
                str(Path(self.temp_dir) / "m.json"),
            ]
        )
        self.assertEqual(rc, 0)
        self.assertFalse(list(self.dest_dir.glob("*")))
        records = json.loads((Path(self.temp_dir) / "m.json").read_text("utf-8"))
        self.assertEqual(records[0]["status"], "dry_run")

    def test_module_main_guard_runs_cli(self) -> None:
        script = Path(__file__).resolve().parent.parent / "main.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--source", result.stdout)


if __name__ == "__main__":
    unittest.main()

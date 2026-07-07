"""Tests for folder_snapshot.py."""

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from folder_snapshot import (
    FileEntry,
    Snapshot,
    DiffResult,
    compute_checksum,
    take_snapshot,
    save_snapshot,
    load_snapshot,
    diff_snapshots,
)


# ---------------------------------------------------------------------------
# compute_checksum
# ---------------------------------------------------------------------------
class TestComputeChecksum:
    def test_returns_hex_string(self, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("some content")
        result = compute_checksum(str(f), "sha256")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_files_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("aaa")
        f2.write_text("bbb")
        assert compute_checksum(str(f1), "sha256") != compute_checksum(str(f2), "sha256")


# ---------------------------------------------------------------------------
# take_snapshot
# ---------------------------------------------------------------------------
class TestTakeSnapshot:
    def test_captures_files(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("hello")
        snap = take_snapshot(str(tmp_path), "sha256", "test", [], no_hash=False)
        assert "file.txt" in snap.files
        assert snap.files["file.txt"].size_bytes == 5

    def test_recursive_capture(self, tmp_path: Path) -> None:
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")
        snap = take_snapshot(str(tmp_path), "sha256", "test", [], no_hash=False)
        assert "sub/nested.txt" in snap.files

    def test_exclusion_applied(self, tmp_path: Path) -> None:
        (tmp_path / "include.txt").write_text("include")
        (tmp_path / "exclude.pyc").write_text("exclude")
        snap = take_snapshot(str(tmp_path), "sha256", "test", ["*.pyc"], no_hash=False)
        assert "include.txt" in snap.files
        assert "exclude.pyc" not in snap.files

    def test_no_hash_skips_checksum(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("data")
        snap = take_snapshot(str(tmp_path), "sha256", "test", [], no_hash=True)
        assert snap.files["file.txt"].checksum == ""


# ---------------------------------------------------------------------------
# save/load snapshot
# ---------------------------------------------------------------------------
class TestSnapshotIO:
    def test_roundtrip(self, tmp_path: Path) -> None:
        snap = Snapshot(root="/src", timestamp="2026-01-01T00:00:00Z", algo="sha256", label="test")
        snap.files["a.txt"] = FileEntry(rel_path="a.txt", size_bytes=100, mtime=1234.5, checksum="abc")
        path = str(tmp_path / "snap.json")
        save_snapshot(snap, path)
        loaded = load_snapshot(path)
        assert loaded.root == "/src"
        assert "a.txt" in loaded.files
        assert loaded.files["a.txt"].checksum == "abc"


# ---------------------------------------------------------------------------
# diff_snapshots
# ---------------------------------------------------------------------------
class TestDiffSnapshots:
    def _snap(self, files: dict) -> Snapshot:
        snap = Snapshot(root="/root", timestamp="T", algo="sha256", label="test")
        for rel, entry in files.items():
            snap.files[rel] = entry
        return snap

    def _entry(self, rel: str, size: int = 100, mtime: float = 1000.0, checksum: str = "abc") -> FileEntry:
        return FileEntry(rel_path=rel, size_bytes=size, mtime=mtime, checksum=checksum)

    def test_added_file(self) -> None:
        old = self._snap({})
        new = self._snap({"new.txt": self._entry("new.txt")})
        result = diff_snapshots(old, new, use_checksum=True)
        assert len(result.added) == 1
        assert result.added[0].rel_path == "new.txt"

    def test_removed_file(self) -> None:
        old = self._snap({"old.txt": self._entry("old.txt")})
        new = self._snap({})
        result = diff_snapshots(old, new, use_checksum=True)
        assert len(result.removed) == 1
        assert result.removed[0].rel_path == "old.txt"

    def test_modified_by_checksum(self) -> None:
        old = self._snap({"f.txt": self._entry("f.txt", checksum="aaa")})
        new = self._snap({"f.txt": self._entry("f.txt", checksum="bbb")})
        result = diff_snapshots(old, new, use_checksum=True)
        assert len(result.modified) == 1

    def test_unchanged_file(self) -> None:
        entry = self._entry("same.txt", checksum="xyz")
        old = self._snap({"same.txt": entry})
        new = self._snap({"same.txt": FileEntry(**entry.__dict__)})
        result = diff_snapshots(old, new, use_checksum=True)
        assert result.unchanged == 1
        assert len(result.modified) == 0

    def test_modified_by_mtime(self) -> None:
        old = self._snap({"f.txt": self._entry("f.txt", size=100, mtime=1000.0)})
        new = self._snap({"f.txt": self._entry("f.txt", size=200, mtime=2000.0)})
        result = diff_snapshots(old, new, use_checksum=False)
        assert len(result.modified) == 1

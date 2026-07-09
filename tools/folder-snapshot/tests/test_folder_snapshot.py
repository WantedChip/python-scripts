"""Tests for folder_snapshot.py."""

# pylint: disable=wrong-import-position,import-error,missing-class-docstring
# pylint: disable=missing-function-docstring,unused-import,too-few-public-methods
import sys
import pytest
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from folder_snapshot import (  # noqa: E402
    FileEntry,
    Snapshot,
    compute_checksum,
    take_snapshot,
    save_snapshot,
    load_snapshot,
    diff_snapshots,
    print_diff,
    snapshot_current_state,
    main,
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
        assert compute_checksum(str(f1), "sha256") != compute_checksum(
            str(f2), "sha256"
        )


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
        snap = Snapshot(
            root="/src", timestamp="2026-01-01T00:00:00Z", algo="sha256", label="test"
        )
        snap.files["a.txt"] = FileEntry(
            rel_path="a.txt", size_bytes=100, mtime=1234.5, checksum="abc"
        )
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

    def _entry(
        self, rel: str, size: int = 100, mtime: float = 1000.0, checksum: str = "abc"
    ) -> FileEntry:
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


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------
def test_compute_checksum_oserror() -> None:
    """Test compute_checksum returns empty string on read error."""
    assert compute_checksum("nonexistent_file_for_checksum_123.bin", "sha256") == ""


def test_take_snapshot_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test take_snapshot handles stat failure by logging and continuing."""
    f = tmp_path / "test.txt"
    f.touch()

    # Mock os.stat to raise OSError
    def mock_stat(path: str) -> os.stat_result:
        raise OSError("Permission denied")

    monkeypatch.setattr(os, "stat", mock_stat)

    snap = take_snapshot(str(tmp_path), "sha256", "test", [], no_hash=False)
    assert len(snap.files) == 0


def test_load_snapshot_errors(tmp_path: Path) -> None:
    """Test load_snapshot handles missing file or parse failures by exiting 1."""
    # 1. Non-existent file
    with pytest.raises(SystemExit) as exc_info:
        load_snapshot("nonexistent_snapshot_file_123.json")
    assert exc_info.value.code == 1

    # 2. Malformed JSON
    bad = tmp_path / "bad.json"
    bad.write_text("invalid json")
    with pytest.raises(SystemExit) as exc_info:
        load_snapshot(str(bad))
    assert exc_info.value.code == 1


def test_snapshot_current_state_errors() -> None:
    """Test snapshot_current_state exits 1 if the reference snapshot root is gone."""
    snap = Snapshot(root="nonexistent_directory_123_abc", timestamp="T", algo="sha256", label="test")
    with pytest.raises(SystemExit) as exc_info:
        snapshot_current_state(snap, "sha256", False)
    assert exc_info.value.code == 1


def test_print_diff(capsys: pytest.CaptureFixture[str]) -> None:
    """Test print_diff helper output format."""
    from folder_snapshot import DiffResult
    diff = DiffResult(
        added=[FileEntry("added.txt", 100, 1000.0, "abc")],
        removed=[FileEntry("removed.txt", 200, 1000.0, "def")],
        modified=[(FileEntry("mod.txt", 100, 1000.0, "abc"), FileEntry("mod.txt", 150, 1000.0, "xyz"))],
        unchanged=10
    )
    print_diff(diff, verbose=True)
    captured = capsys.readouterr()
    assert "Added (1)" in captured.out
    assert "Removed (1)" in captured.out
    assert "Modified (1)" in captured.out
    assert "Unchanged: 10" in captured.out


def test_main_cli_execution(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test main command-line operations (snapshot and diff)."""
    # 1. snapshot command on nonexistent dir exits 1
    with pytest.raises(SystemExit) as exc_info:
        main(["snapshot", "--root", "nonexistent_dir_123", "--output", "out.json"])
    assert exc_info.value.code == 1

    # 2. successful snapshot creation
    src = tmp_path / "src"
    src.mkdir()
    (src / "file.txt").write_text("hello")
    snap_out = tmp_path / "snap.json"
    
    main(["snapshot", "--root", str(src), "--output", str(snap_out)])
    assert snap_out.exists()

    # 3. successful diff command
    snap_out_2 = tmp_path / "snap2.json"
    (src / "file2.txt").write_text("world")
    main(["snapshot", "--root", str(src), "--output", str(snap_out_2)])

    main(["diff", "--old", str(snap_out), "--new", str(snap_out_2)])
    captured = capsys.readouterr()
    assert "file2.txt" in captured.out

    # 4. diff live command
    main(["diff", "--old", str(snap_out), "--live"])
    captured_live = capsys.readouterr()
    assert "file2.txt" in captured_live.out

    # 5. diff usage error without live or new exits 1
    with pytest.raises(SystemExit) as exc_info:
        main(["diff", "--old", str(snap_out)])
    assert exc_info.value.code == 1

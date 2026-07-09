"""Tests for smart_backup.py."""

# pylint: disable=wrong-import-position,import-error,missing-class-docstring
# pylint: disable=missing-function-docstring,unused-import
import os
import sys
import time
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smart_backup import (  # noqa: E402
    BackupManifest,
    FileRecord,
    compute_checksum,
    matches_exclusion,
    load_manifest,
    save_manifest,
    collect_source_files,
    run_backup,
    verify_backup,
    apply_retention,
    main,
)


# ---------------------------------------------------------------------------
# compute_checksum
# ---------------------------------------------------------------------------
class TestComputeChecksum:
    def test_sha256(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        cs = compute_checksum(str(f), "sha256")
        assert len(cs) == 64  # SHA-256 hex digest length

    def test_md5(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        cs = compute_checksum(str(f), "md5")
        assert len(cs) == 32

    def test_deterministic(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("same content")
        cs1 = compute_checksum(str(f), "sha256")
        cs2 = compute_checksum(str(f), "sha256")
        assert cs1 == cs2

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A")
        f2.write_text("content B")
        assert compute_checksum(str(f1), "sha256") != compute_checksum(
            str(f2), "sha256"
        )


# ---------------------------------------------------------------------------
# matches_exclusion
# ---------------------------------------------------------------------------
class TestMatchesExclusion:
    def test_filename_glob(self) -> None:
        assert matches_exclusion("dir/file.pyc", ["*.pyc"])

    def test_directory_name(self) -> None:
        assert matches_exclusion("__pycache__/module.cpython.pyc", ["__pycache__"])

    def test_no_match(self) -> None:
        assert not matches_exclusion("src/main.py", ["*.pyc", "__pycache__"])

    def test_exact_match(self) -> None:
        assert matches_exclusion(".git/HEAD", [".git"])


# ---------------------------------------------------------------------------
# manifest save/load
# ---------------------------------------------------------------------------
class TestManifest:
    def test_save_and_load(self, tmp_path: Path) -> None:
        manifest = BackupManifest(
            timestamp="2026-01-01T00:00:00Z",
            source="/src",
            destination="/dest",
            algo="sha256",
        )
        manifest.files.append(
            FileRecord(
                rel_path="file.txt",
                size_bytes=100,
                mtime=1234567890.0,
                checksum="abc123",
                algo="sha256",
            )
        )
        path = str(tmp_path / "manifest.json")
        save_manifest(manifest, path)
        loaded = load_manifest(path)
        assert loaded is not None
        assert loaded.timestamp == manifest.timestamp
        assert len(loaded.files) == 1
        assert loaded.files[0].rel_path == "file.txt"

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        result = load_manifest(str(tmp_path / "nonexistent.json"))
        assert result is None


# ---------------------------------------------------------------------------
# collect_source_files
# ---------------------------------------------------------------------------
class TestCollectSourceFiles:
    def test_basic_collection(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.py").write_text("b")
        files = collect_source_files(str(tmp_path), [])
        rel_paths = [r for _, r in files]
        assert "a.txt" in rel_paths
        assert "b.py" in rel_paths

    def test_exclusion_applied(self, tmp_path: Path) -> None:
        (tmp_path / "keep.txt").write_text("keep")
        (tmp_path / "exclude.pyc").write_text("exclude")
        files = collect_source_files(str(tmp_path), ["*.pyc"])
        rel_paths = [r for _, r in files]
        assert "keep.txt" in rel_paths
        assert "exclude.pyc" not in rel_paths

    def test_subdirectory_excluded(self, tmp_path: Path) -> None:
        subdir = tmp_path / "__pycache__"
        subdir.mkdir()
        (subdir / "module.pyc").write_text("x")
        (tmp_path / "main.py").write_text("main")
        files = collect_source_files(str(tmp_path), ["__pycache__"])
        rel_paths = [r for _, r in files]
        assert "main.py" in rel_paths
        assert not any("__pycache__" in r for r in rel_paths)


# ---------------------------------------------------------------------------
# run_backup (integration)
# ---------------------------------------------------------------------------
class TestRunBackup:
    def test_copies_new_files(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "hello.txt").write_text("hello world")

        run_backup(
            source=str(src),
            destination=str(dst),
            exclude_patterns=[],
            mode="mtime",
            algo="sha256",
            dry_run=False,
        )

        assert (dst / "hello.txt").exists()

    def test_dry_run_no_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "hello.txt").write_text("hello world")

        run_backup(
            source=str(src),
            destination=str(dst),
            exclude_patterns=[],
            mode="mtime",
            algo="sha256",
            dry_run=True,
        )

        # Should not actually copy in dry-run
        assert not (dst / "hello.txt").exists()

    def test_incremental_skip_unchanged(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        f = src / "file.txt"
        f.write_text("content")

        # First backup
        run_backup(str(src), str(dst), [], "mtime", "sha256", False)
        mtime_after_first = os.path.getmtime(str(dst / "file.txt"))

        # Second backup with no changes
        time.sleep(0.05)  # Ensure time passes
        run_backup(str(src), str(dst), [], "mtime", "sha256", False)
        mtime_after_second = os.path.getmtime(str(dst / "file.txt"))

        # The destination file should NOT have been re-copied (mtime unchanged)
        assert mtime_after_first == mtime_after_second


# ---------------------------------------------------------------------------
# verify_backup
# ---------------------------------------------------------------------------
class TestVerifyBackup:
    def test_passes_on_intact_backup(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "data.txt").write_text("data content")

        run_backup(str(src), str(dst), [], "checksum", "sha256", False)
        ok = verify_backup(str(dst), "sha256")
        assert ok is True

    def test_fails_on_tampered_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "data.txt").write_text("original")

        run_backup(str(src), str(dst), [], "checksum", "sha256", False)
        # Tamper with the destination file
        (dst / "data.txt").write_text("tampered!")
        ok = verify_backup(str(dst), "sha256")
        assert ok is False


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------
def test_load_manifest_errors(tmp_path: Path) -> None:
    """Test load_manifest handles malformed JSON or missing keys."""
    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text("invalid json{")
    assert load_manifest(str(bad_manifest)) is None


def test_compute_checksum_oserror() -> None:
    """Test compute_checksum raises OSError if file cannot be read."""
    with pytest.raises(OSError):
        compute_checksum("nonexistent_file_for_checksum_123.bin")


def test_run_backup_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_backup logs an error if source files trigger an OSError."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    
    f = src / "fail.txt"
    f.touch()

    # Mock os.path.getsize to raise OSError
    def mock_getsize(path: str) -> int:
        raise OSError("Permission denied")

    monkeypatch.setattr(os.path, "getsize", mock_getsize)

    manifest = run_backup(str(src), str(dst), [], "mtime", "sha256", False)
    assert len(manifest.files) == 0


def test_verify_backup_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test verify_backup behavior on missing files or checksum read errors."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "data.txt").write_text("original")

    run_backup(str(src), str(dst), [], "checksum", "sha256", False)

    # 1. Missing file in destination
    os.remove(str(dst / "data.txt"))
    assert verify_backup(str(dst), "sha256") is False

    # 2. OSError during compute_checksum
    (dst / "data.txt").write_text("recreated")
    import builtins
    original_open = builtins.open
    def mock_open(file, *args, **kwargs):
        if "manifest" in str(file):
            return original_open(file, *args, **kwargs)
        raise OSError("Read error")
    monkeypatch.setattr(builtins, "open", mock_open)
    assert verify_backup(str(dst), "sha256") is False


def test_apply_retention(tmp_path: Path) -> None:
    """Test retention policy clears old backup subdirectories by name date."""
    # Retain for 5 days
    cutoff_old = tmp_path / "2026-01-01_backup"
    cutoff_old.mkdir()
    
    recent = tmp_path / "2026-07-08_backup"
    recent.mkdir()

    not_a_backup = tmp_path / "not-a-date"
    not_a_backup.mkdir()

    # Retention keep_days is calculated from datetime.utcnow().
    # Let's mock cutoff to be older than 2026-01-01
    apply_retention(str(tmp_path), keep_days=1, dry_run=False)

    # 2026-01-01 is old, so it should be deleted.
    # 2026-07-08 is recent, so it should keep it.
    # non-dated should be skipped.
    assert not cutoff_old.exists()
    assert recent.exists()
    assert not_a_backup.exists()


def test_main_cli_execution(tmp_path: Path) -> None:
    """Test main function CLI entry point scenarios."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "hello.txt").write_text("hello")

    # 1. No arguments should raise argparse validation error and exit 2
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 2

    # 2. Nonexistent source exits 1
    with pytest.raises(SystemExit) as exc_info:
        main(["--source", "nonexistent_source_dir_123", "--dest", str(dst)])
    assert exc_info.value.code == 1

    # 3. Successful run with verification
    main(["--source", str(src), "--dest", str(dst), "--verify"])
    assert (dst / "hello.txt").exists()
    assert (dst / ".backup_manifest.json").exists()

    # 4. Successful retention call
    main(["--dest", str(tmp_path), "--apply-retention", "--keep-days", "10"])

"""Unit tests for File Quarantine Cleaner."""

import sys
import time
from pathlib import Path

# noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest  # noqa: E402
from file_quarantine_cleaner.main import (  # noqa: E402
    format_size,
    get_file_info,
    main,
    run_cleanup,
    scan_directory,
)


def test_format_size() -> None:
    """Test format_size human readable calculations."""
    assert format_size(500) == "500 B"
    assert format_size(1500) == "1.46 KB"
    assert format_size(1500000) == "1.43 MB"
    assert format_size(1500000000) == "1.40 GB"


def test_get_file_info_invalid(tmp_path: Path) -> None:
    """Test get_file_info handles missing files gracefully."""
    non_existent = tmp_path / "missing.txt"
    info = get_file_info(non_existent, time.time())
    assert info == {}


def test_scan_directory_and_heuristics(tmp_path: Path) -> None:
    """Test directory scanning finds matching categories and obeys excludes."""
    # Create test files
    installer = tmp_path / "setup.exe"
    installer.touch()

    archive = tmp_path / "archive.tar.gz"
    archive.touch()

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "temp.log"
    cache_file.touch()

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    git_file = git_dir / "index"
    git_file.touch()

    # Old abandoned download
    abandoned = tmp_path / "old_doc.txt"
    abandoned.touch()
    # Backdate mtime to 40 days ago
    old_time = time.time() - 40 * 24 * 3600
    os_utime = getattr(time, "utime", None)
    if os_utime is None:
        import os

        os.utime(abandoned, (old_time, old_time))
    else:
        import os

        os.utime(str(abandoned), (old_time, old_time))

    current_time = time.time()
    files = scan_directory(
        tmp_path,
        days_threshold=30.0,
        excludes=[],
        categories_filter=set(),
        current_time=current_time,
    )

    # We expect: installer, archive, cache_file, abandoned
    # .git/index should be excluded by default
    paths = [f["path"] for f in files]
    assert installer in paths
    assert archive in paths
    assert cache_file in paths
    assert abandoned in paths
    assert git_file not in paths

    # Verify categories
    for f in files:
        if f["path"] == installer:
            assert "installer" in f["categories"]
        if f["path"] == archive:
            assert "archive" in f["categories"]
        if f["path"] == cache_file:
            assert "cache" in f["categories"]
        if f["path"] == abandoned:
            assert "abandoned" in f["categories"]


def test_scan_directory_filters(tmp_path: Path) -> None:
    """Test scanner obeys category and custom pattern filters."""
    installer = tmp_path / "setup.exe"
    installer.touch()
    archive = tmp_path / "archive.zip"
    archive.touch()

    current_time = time.time()

    # Category filter
    files_installer = scan_directory(
        tmp_path,
        days_threshold=30.0,
        excludes=[],
        categories_filter={"installer"},
        current_time=current_time,
    )
    assert len(files_installer) == 1
    assert files_installer[0]["path"] == installer

    # Custom excludes
    files_exclude = scan_directory(
        tmp_path,
        days_threshold=30.0,
        excludes=["*.exe"],
        categories_filter=set(),
        current_time=current_time,
    )
    assert len(files_exclude) == 1
    assert files_exclude[0]["path"] == archive


def test_scan_directory_missing() -> None:
    """Test scan_directory returns empty list on invalid path."""
    assert scan_directory(Path("missing_dir_123"), 30, [], set(), time.time()) == []


def test_run_cleanup_dry_run_and_force(tmp_path: Path) -> None:
    """Test cleanup actions in dry-run and force modes."""
    file1 = tmp_path / "file1.txt"
    file1.touch()

    files = [
        {
            "path": file1,
            "size": 100,
            "age_days": 10.0,
            "categories": ["abandoned"],
        }
    ]

    # Dry-run clean
    count, size = run_cleanup(files, quarantine_dir=None, dry_run=True, force=True)
    assert count == 1
    assert size == 100
    assert file1.exists()

    # Real force clean
    count, size = run_cleanup(files, quarantine_dir=None, dry_run=False, force=True)
    assert count == 1
    assert size == 100
    assert not file1.exists()


def test_run_cleanup_quarantine(tmp_path: Path) -> None:
    """Test cleanup moves files to quarantine directory."""
    file1 = tmp_path / "file1.txt"
    file1.touch()
    quarantine = tmp_path / "quarantine"

    files = [
        {
            "path": file1,
            "size": 100,
            "age_days": 10.0,
            "categories": ["abandoned"],
        }
    ]

    # Real force quarantine
    count, size = run_cleanup(
        files, quarantine_dir=quarantine, dry_run=False, force=True
    )
    assert count == 1
    assert size == 100
    assert not file1.exists()
    assert (quarantine / "file1.txt").exists()


def test_run_cleanup_quarantine_conflict(tmp_path: Path) -> None:
    """Test cleanup resolves filename conflicts in quarantine folder."""
    file1 = tmp_path / "file1.txt"
    file1.touch()
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir()
    (quarantine / "file1.txt").touch()  # Existing conflict

    files = [
        {
            "path": file1,
            "size": 100,
            "age_days": 10.0,
            "categories": ["abandoned"],
        }
    ]

    # Real force quarantine
    count, size = run_cleanup(
        files, quarantine_dir=quarantine, dry_run=False, force=True
    )
    assert count == 1
    assert not file1.exists()
    assert (quarantine / "file1_1.txt").exists()


def test_run_cleanup_interactive_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test cleanup interactive prompt confirmation Choice: all yes."""
    file1 = tmp_path / "file1.txt"
    file1.touch()

    files = [
        {
            "path": file1,
            "size": 100,
            "age_days": 10.0,
            "categories": ["abandoned"],
        }
    ]

    # User inputs "y" (Clean all detected files)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    count, size = run_cleanup(files, quarantine_dir=None, dry_run=False, force=False)
    assert count == 1
    assert size == 100
    assert not file1.exists()


def test_run_cleanup_interactive_no(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test cleanup interactive prompt confirmation Choice: abort."""
    file1 = tmp_path / "file1.txt"
    file1.touch()

    files = [
        {
            "path": file1,
            "size": 100,
            "age_days": 10.0,
            "categories": ["abandoned"],
        }
    ]

    # User inputs "n" (Abort cleanup)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    count, size = run_cleanup(files, quarantine_dir=None, dry_run=False, force=False)
    assert count == 0
    assert size == 0
    assert file1.exists()


def test_run_cleanup_interactive_individual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test cleanup interactive individual prompts Choice: yes/no for each file."""
    file1 = tmp_path / "file1.txt"
    file1.touch()
    file2 = tmp_path / "file2.txt"
    file2.touch()

    files = [
        {
            "path": file1,
            "size": 100,
            "age_days": 10.0,
            "categories": ["abandoned"],
        },
        {
            "path": file2,
            "size": 200,
            "age_days": 10.0,
            "categories": ["abandoned"],
        },
    ]

    # First prompt: "i" (Interactive confirmation)
    # Second prompt (file2 - sorted by size): "y" (confirm)
    # Third prompt (file1): "n" (deny)
    inputs = ["i", "y", "n"]
    monkeypatch.setattr("builtins.input", lambda _: inputs.pop(0))

    count, size = run_cleanup(files, quarantine_dir=None, dry_run=False, force=False)
    assert count == 1
    assert size == 200
    assert not file2.exists()
    assert file1.exists()


def test_run_cleanup_interactive_abort_handling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test cleanup interactive mode handles KeyboardInterrupt gracefully."""
    file1 = tmp_path / "file1.txt"
    file1.touch()

    files = [
        {
            "path": file1,
            "size": 100,
            "age_days": 10.0,
            "categories": ["abandoned"],
        }
    ]

    def mock_input_interrupt(prompt: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", mock_input_interrupt)
    count, size = run_cleanup(files, quarantine_dir=None, dry_run=False, force=False)
    assert count == 0
    assert size == 0
    assert file1.exists()


def test_run_cleanup_empty() -> None:
    """Test run_cleanup returns early on empty file list."""
    assert run_cleanup([], None, False, False) == (0, 0)


def test_cli_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full CLI main entry routing."""
    file1 = tmp_path / "file1.tmp"
    file1.touch()

    # Target arguments
    args = [
        "file_quarantine_cleaner",
        str(tmp_path),
        "--days",
        "0",
        "--category",
        "cache",
        "--force",
        "--verbose",
    ]
    monkeypatch.setattr(sys, "argv", args)
    main()
    assert not file1.exists()


def test_cli_main_invalid_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI main exits on invalid directory."""
    args = [
        "file_quarantine_cleaner",
        "invalid_dir_123_xyz",
    ]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1

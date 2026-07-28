"""Unit tests for screenshot_organizer module."""

import sys
from pathlib import Path

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from screenshot_organizer import (  # noqa: E402
    is_screenshot_file,
    main,
    organize_screenshots,
)


def test_is_screenshot_file() -> None:
    """Test identifying screenshot file names."""
    assert is_screenshot_file(Path("Screenshot 2026-07-28.png")) is True
    assert is_screenshot_file(Path("scrn_001.jpg")) is True
    assert is_screenshot_file(Path("vacation_photo.jpg")) is False


def test_organize_screenshots(tmp_path: Path) -> None:
    """Test organizing screenshots into date subfolders."""
    src_dir = tmp_path / "raw"
    dst_dir = tmp_path / "organized"
    src_dir.mkdir()

    scrn = src_dir / "Screenshot_1.png"
    scrn.write_text("dummy image data")

    moved, skipped = organize_screenshots(src_dir, dst_dir)
    assert moved == 1
    assert skipped == 0
    assert not scrn.exists()


def test_cli_dry_run(tmp_path: Path) -> None:
    """Test CLI dry-run option."""
    src_dir = tmp_path / "raw_cli"
    src_dir.mkdir()
    scrn = src_dir / "Screenshot_test.png"
    scrn.write_text("test data")

    ret = main([str(src_dir), "--dry-run", "-v"])
    assert ret == 0
    assert scrn.exists()

"""Unit tests for screenshot_organizer end-to-end behaviors."""

import sys
from pathlib import Path
from unittest.mock import patch

# Ensure the src folder is on sys.path so imports resolve to the src-layout
# package consistently with test_main.py within the same pytest process.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from screenshot_organizer.main import ScreenshotOrganizer, main  # noqa: E402


def test_get_image_files_filters_images(tmp_path: Path) -> None:
    """Test scanning only picks up supported image files."""
    src_dir = tmp_path / "raw"
    src_dir.mkdir()
    (src_dir / "Screenshot 2026-07-28.png").write_text("img", encoding="utf-8")
    (src_dir / "scrn_001.jpg").write_text("img", encoding="utf-8")
    (src_dir / "notes.txt").write_text("text", encoding="utf-8")

    organizer = ScreenshotOrganizer(src_dir, tmp_path / "dst")
    found = {f.name for f in organizer.get_image_files()}

    assert found == {"Screenshot 2026-07-28.png", "scrn_001.jpg"}


def test_organize_moves_screenshots(tmp_path: Path) -> None:
    """Test organizing moves screenshots out of the source directory."""
    src_dir = tmp_path / "raw"
    dst_dir = tmp_path / "organized"
    src_dir.mkdir()

    scrn = src_dir / "Screenshot_1.png"
    scrn.write_text("dummy image data", encoding="utf-8")

    organizer = ScreenshotOrganizer(src_dir, dst_dir)
    organizer.organize()

    assert not scrn.exists()
    organized = list(dst_dir.rglob("Screenshot_1.png"))
    assert len(organized) == 1


def test_cli_dry_run(tmp_path: Path) -> None:
    """Test CLI dry-run previews operations without moving files."""
    src_dir = tmp_path / "raw_cli"
    dst_dir = tmp_path / "organized_cli"
    src_dir.mkdir()
    scrn = src_dir / "Screenshot_test.png"
    scrn.write_text("test data", encoding="utf-8")

    argv = [
        "screenshot_organizer.main",
        str(src_dir),
        str(dst_dir),
        "--dry-run",
        "-v",
    ]
    with patch("sys.argv", argv):
        main()

    assert scrn.exists()
    assert list(dst_dir.rglob("Screenshot_test.png")) == []

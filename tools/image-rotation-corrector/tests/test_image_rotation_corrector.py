"""Unit tests for image_rotation_corrector module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_rotation_corrector import correct_image_orientation, main  # noqa: E402


def test_correct_image_orientation(tmp_path: Path) -> None:
    """Test orientation correction function."""
    src = tmp_path / "sample.jpg"
    dst = tmp_path / "upright.jpg"

    img = Image.new("RGB", (100, 200), color="blue")
    img.save(src)

    ok = correct_image_orientation(src, dst)
    assert ok is True
    assert dst.exists()


def test_correct_image_orientation_rgba(tmp_path: Path) -> None:
    """Test orientation correction for RGBA JPEG file output."""
    src = tmp_path / "rgba.jpg"
    dst = tmp_path / "out_rgba.jpg"

    img = Image.new("RGBA", (50, 50), color=(255, 0, 0, 255))
    img.save(src, format="PNG")

    ok = correct_image_orientation(src, dst)
    assert ok is True
    assert dst.exists()


def test_cli_in_place(tmp_path: Path) -> None:
    """Test CLI --in-place execution."""
    src = tmp_path / "photo.png"
    img = Image.new("RGB", (50, 50), color="red")
    img.save(src)

    ret = main([str(src), "--in-place", "-v"])
    assert ret == 0
    assert src.exists()


def test_cli_directory_batch(tmp_path: Path) -> None:
    """Test CLI batch directory processing."""
    in_dir = tmp_path / "photos"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    img = Image.new("RGB", (60, 60), color="green")
    img.save(in_dir / "pic.jpg")

    ret = main([str(in_dir), "-o", str(out_dir), "-v"])
    assert ret == 0
    assert (out_dir / "pic_upright.jpg").exists()

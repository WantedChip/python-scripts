"""Unit tests for image_metadata_stripper module."""

import sys
from pathlib import Path

from PIL import Image, PngImagePlugin

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_metadata_stripper import main, strip_metadata  # noqa: E402


def test_strip_metadata(tmp_path: Path) -> None:
    """Test stripping metadata from an image file."""
    src = tmp_path / "dirty.png"
    dst = tmp_path / "clean.png"

    # Create image with PNG metadata info
    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "TestUser")
    info.add_text("Location", "GPS 37.7749,-122.4194")

    img = Image.new("RGB", (100, 100), color="red")
    img.save(src, pnginfo=info)

    # Verify original has info text
    with Image.open(src) as dirty_img:
        assert "Author" in dirty_img.info

    res = strip_metadata(src, dst)
    assert res is True
    assert dst.exists()

    with Image.open(dst) as clean_img:
        assert "Author" not in clean_img.info
        assert "Location" not in clean_img.info


def test_strip_metadata_jpg(tmp_path: Path) -> None:
    """Test stripping metadata for JPEG format."""
    src = tmp_path / "sample.jpg"
    dst = tmp_path / "clean.jpg"

    img = Image.new("RGB", (80, 80), color=(0, 255, 0))
    img.save(src, format="JPEG")

    res = strip_metadata(src, dst)
    assert res is True
    assert dst.exists()


def test_cli_in_place(tmp_path: Path) -> None:
    """Test CLI --in-place stripping mode."""
    src = tmp_path / "photo.jpg"
    img = Image.new("RGB", (50, 50), color="blue")
    img.save(src)

    ret = main([str(src), "--in-place", "-v"])
    assert ret == 0
    assert src.exists()


def test_cli_directory_batch(tmp_path: Path) -> None:
    """Test CLI batch directory processing."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    img = Image.new("RGB", (60, 60), color="white")
    img.save(in_dir / "item.jpg")

    ret = main([str(in_dir), "-o", str(out_dir), "--suffix", "_clean", "-v"])
    assert ret == 0
    assert (out_dir / "item_clean.jpg").exists()

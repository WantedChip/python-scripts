"""Unit tests for image_thumbnail_generator module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_thumbnail_generator import generate_thumbnail, main  # noqa: E402


def test_generate_thumbnail_aspect(tmp_path: Path) -> None:
    """Test generating thumbnail preserving aspect ratio."""
    src = tmp_path / "large.jpg"
    dst = tmp_path / "large_thumb.jpg"

    img = Image.new("RGB", (1000, 500), color="blue")
    img.save(src)

    ok = generate_thumbnail(src, dst, max_size=(200, 200))
    assert ok is True
    assert dst.exists()

    with Image.open(dst) as thumb:
        assert thumb.size == (200, 100)


def test_generate_thumbnail_square(tmp_path: Path) -> None:
    """Test padded square thumbnail generation."""
    src = tmp_path / "wide.png"
    dst = tmp_path / "wide_thumb.png"

    img = Image.new("RGBA", (800, 400), color=(255, 0, 0, 255))
    img.save(src)

    ok = generate_thumbnail(src, dst, max_size=(200, 200), square=True)
    assert ok is True

    with Image.open(dst) as thumb:
        assert thumb.size == (200, 200)


def test_cli_directory(tmp_path: Path) -> None:
    """Test CLI batch thumbnail generation."""
    in_dir = tmp_path / "pics"
    out_dir = tmp_path / "thumbs"
    in_dir.mkdir()

    img = Image.new("RGB", (500, 500), color="green")
    img.save(in_dir / "photo.jpg")

    ret = main([str(in_dir), "-o", str(out_dir), "-s", "128", "--square", "-v"])
    assert ret == 0
    assert (out_dir / "photo_thumb.jpg").exists()

    with Image.open(out_dir / "photo_thumb.jpg") as thumb:
        assert thumb.size == (128, 128)

"""Unit tests for image_grayscale_converter module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_grayscale_converter import convert_to_grayscale, main  # noqa: E402


def test_convert_to_grayscale(tmp_path: Path) -> None:
    """Test converting a color image to grayscale."""
    src = tmp_path / "color.png"
    dst = tmp_path / "gray.png"

    img = Image.new("RGB", (100, 100), color="red")
    img.save(src)

    ok = convert_to_grayscale(src, dst, contrast_factor=1.2)
    assert ok is True
    assert dst.exists()

    with Image.open(dst) as converted:
        assert converted.mode in ("L", "RGB")


def test_convert_to_sepia(tmp_path: Path) -> None:
    """Test sepia tone filter conversion."""
    src = tmp_path / "color.jpg"
    dst = tmp_path / "sepia.jpg"

    img = Image.new("RGB", (80, 80), color="blue")
    img.save(src)

    ok = convert_to_grayscale(src, dst, sepia=True)
    assert ok is True
    assert dst.exists()


def test_cli_directory(tmp_path: Path) -> None:
    """Test CLI batch grayscale directory conversion."""
    in_dir = tmp_path / "photos"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    img = Image.new("RGB", (50, 50), color="yellow")
    img.save(in_dir / "sample.jpg")

    ret = main([str(in_dir), "-o", str(out_dir), "-c", "1.5", "-v"])
    assert ret == 0
    assert (out_dir / "sample_gray.jpg").exists()

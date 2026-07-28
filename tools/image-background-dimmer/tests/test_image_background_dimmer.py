"""Unit tests for image_background_dimmer module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_background_dimmer import dim_image_background, main  # noqa: E402


def test_dim_image_background(tmp_path: Path) -> None:
    """Test dimming background of an image."""
    src = tmp_path / "bright.jpg"
    dst = tmp_path / "dimmed.jpg"

    img = Image.new("RGB", (100, 100), color="white")
    img.save(src)

    ok = dim_image_background(src, dst, dim_factor=0.5, opacity=0.3)
    assert ok is True
    assert dst.exists()

    with Image.open(dst) as dimmed:
        # White image dimmed should have lower average pixel brightness
        r, g, b = dimmed.getpixel((50, 50))
        assert r < 255 and g < 255 and b < 255


def test_cli_execution(tmp_path: Path) -> None:
    """Test CLI batch background dimming."""
    in_dir = tmp_path / "photos"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    img = Image.new("RGB", (50, 50), color="red")
    img.save(in_dir / "test.png")

    ret = main([str(in_dir), "-o", str(out_dir), "-d", "0.4", "-v"])
    assert ret == 0
    assert (out_dir / "test_dimmed.png").exists()

"""Unit tests for image_border_adder module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_border_adder import add_image_border, main, parse_hex_color  # noqa: E402


def test_parse_hex_color() -> None:
    """Test hex color string parsing helper."""
    assert parse_hex_color("#FF0000") == (255, 0, 0)
    assert parse_hex_color("black") == (0, 0, 0)
    assert parse_hex_color("white") == (255, 255, 255)


def test_add_image_border(tmp_path: Path) -> None:
    """Test adding uniform border around an image."""
    src = tmp_path / "base.png"
    dst = tmp_path / "bordered.png"

    img = Image.new("RGB", (100, 100), color="blue")
    img.save(src)

    ok = add_image_border(src, dst, border_width=10, border_color=(255, 255, 255))
    assert ok is True
    assert dst.exists()

    with Image.open(dst) as bordered:
        # Original 100x100 + 10px on all 4 sides = 120x120
        assert bordered.size == (120, 120)


def test_add_polaroid_border(tmp_path: Path) -> None:
    """Test polaroid wide bottom border."""
    src = tmp_path / "photo.jpg"
    dst = tmp_path / "polaroid.jpg"

    img = Image.new("RGB", (200, 200), color="green")
    img.save(src)

    ok = add_image_border(src, dst, border_width=15, polaroid=True, bottom_margin=50)
    assert ok is True

    with Image.open(dst) as res:
        # Width: 200 + 15 + 15 = 230; Height: 200 + 15 + (15 + 50) = 280
        assert res.size == (230, 280)


def test_cli_execution(tmp_path: Path) -> None:
    """Test CLI batch border processing."""
    in_dir = tmp_path / "pics"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    img = Image.new("RGB", (50, 50), color="yellow")
    img.save(in_dir / "sample.jpg")

    ret = main([str(in_dir), "-o", str(out_dir), "-w", "5", "-v"])
    assert ret == 0
    assert (out_dir / "sample_border.jpg").exists()

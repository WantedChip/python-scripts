"""Unit tests for image_collage_maker module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_collage_maker import create_collage, main, parse_hex_color  # noqa: E402


def test_parse_hex_color() -> None:
    """Test hex color string parsing."""
    assert parse_hex_color("#000000") == (0, 0, 0)
    assert parse_hex_color("black") == (0, 0, 0)
    assert parse_hex_color("#FF8800") == (255, 136, 0)


def test_create_collage(tmp_path: Path) -> None:
    """Test assembling images into a collage file."""
    img1_path = tmp_path / "img1.png"
    img2_path = tmp_path / "img2.png"
    out_path = tmp_path / "collage.jpg"

    Image.new("RGB", (200, 200), color="red").save(img1_path)
    Image.new("RGB", (200, 200), color="blue").save(img2_path)

    ok = create_collage(
        [img1_path, img2_path],
        out_path,
        cols=2,
        cell_size=(100, 100),
        spacing=10,
    )
    assert ok is True
    assert out_path.exists()

    with Image.open(out_path) as col:
        # 2 cols: spacing(10) + cell(100) + spacing(10) + cell(100) + spacing(10) = 230
        assert col.size[0] == 230


def test_cli_execution(tmp_path: Path) -> None:
    """Test CLI collage maker command."""
    in_dir = tmp_path / "photos"
    in_dir.mkdir()
    out_file = tmp_path / "out.png"

    Image.new("RGB", (150, 150), color="green").save(in_dir / "p1.jpg")
    Image.new("RGB", (150, 150), color="yellow").save(in_dir / "p2.jpg")

    ret = main([str(in_dir), "-o", str(out_file), "-c", "2", "-v"])
    assert ret == 0
    assert out_file.exists()

"""Unit tests for image_format_converter module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_format_converter import (  # noqa: E402
    convert_image_format,
    main,
    parse_hex_color,
)


def test_parse_hex_color() -> None:
    """Test hex color parsing into RGB tuples."""
    assert parse_hex_color("#FF0000") == (255, 0, 0)
    assert parse_hex_color("00FF00") == (0, 255, 0)
    assert parse_hex_color("invalid") == (255, 255, 255)


def test_convert_png_to_jpg(tmp_path: Path) -> None:
    """Test converting PNG to JPG with transparency flattening."""
    png_file = tmp_path / "transparent.png"
    jpg_file = tmp_path / "out.jpg"

    # Create RGBA image with alpha
    img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
    img.save(png_file)

    res = convert_image_format(png_file, jpg_file, target_format="jpg")
    assert res is True
    assert jpg_file.exists()

    with Image.open(jpg_file) as converted:
        assert converted.format == "JPEG"
        assert converted.mode == "RGB"


def test_cli_batch_convert(tmp_path: Path) -> None:
    """Test CLI batch directory format conversion."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    img1 = Image.new("RGB", (50, 50), color="red")
    img1.save(in_dir / "sample.bmp")

    ret = main([str(in_dir), "-o", str(out_dir), "-f", "webp", "-v"])
    assert ret == 0
    assert (out_dir / "sample.webp").exists()

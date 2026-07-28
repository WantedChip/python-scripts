"""Unit tests for image_color_palette_extractor module."""

import sys
from pathlib import Path

import pytest
from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_color_palette_extractor import (  # noqa: E402
    extract_color_palette,
    format_ansi_swatch,
    main,
    rgb_to_hex,
)


def test_rgb_to_hex() -> None:
    """Test RGB to hex conversion helper."""
    assert rgb_to_hex(255, 0, 0) == "#FF0000"
    assert rgb_to_hex(0, 255, 0) == "#00FF00"
    assert rgb_to_hex(0, 0, 0) == "#000000"


def test_extract_color_palette(tmp_path: Path) -> None:
    """Test extracting dominant colors from a sample image."""
    img_path = tmp_path / "sample.png"

    img = Image.new("RGB", (100, 100), color="red")
    img.save(img_path)

    palette = extract_color_palette(img_path, num_colors=3)
    assert len(palette) > 0
    assert "hex" in palette[0]
    assert "percentage" in palette[0]


def test_cli_json_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test CLI JSON export output."""
    img_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (60, 60), color="green")
    img.save(img_path)

    ret = main([str(img_path), "-f", "json", "-n", "3"])
    assert ret == 0
    captured = capsys.readouterr()
    assert '"hex"' in captured.out


def test_cli_csv_and_table_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test CLI CSV and default table format outputs."""
    img_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (60, 60), color="blue")
    img.save(img_path)

    ret1 = main([str(img_path), "-f", "csv", "-v"])
    assert ret1 == 0
    cap1 = capsys.readouterr()
    assert "HEX,RGB,PERCENTAGE" in cap1.out

    ret2 = main([str(img_path), "-f", "table"])
    assert ret2 == 0
    cap2 = capsys.readouterr()
    assert "Dominant Color Palette" in cap2.out


def test_format_ansi_swatch() -> None:
    """Test ANSI color swatch generation."""
    swatch = format_ansi_swatch(255, 0, 0)
    assert "\033[48;2;255;0;0m" in swatch

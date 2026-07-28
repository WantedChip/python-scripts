"""Unit tests for image_crop_center module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_crop_center import calculate_crop_box, crop_image_center, main  # noqa: E402


def test_calculate_crop_box() -> None:
    """Test crop bounding box math for square and widescreen ratios."""
    # 1:1 square crop of 1000x500
    box_sq = calculate_crop_box(1000, 500, 1.0, 1.0)
    assert box_sq == (250, 0, 750, 500)

    # 16:9 crop of 1000x1000
    box_169 = calculate_crop_box(1000, 1000, 16.0, 9.0)
    assert box_169[2] - box_169[0] == 1000
    assert box_169[3] - box_169[1] == 562


def test_crop_image_center(tmp_path: Path) -> None:
    """Test cropping image to 1:1 ratio."""
    src = tmp_path / "wide.png"
    dst = tmp_path / "square.png"

    img = Image.new("RGB", (800, 400), color="purple")
    img.save(src)

    ok = crop_image_center(src, dst, aspect_ratio="1:1")
    assert ok is True
    assert dst.exists()

    with Image.open(dst) as cropped:
        assert cropped.size == (400, 400)


def test_cli_directory(tmp_path: Path) -> None:
    """Test CLI batch center cropping."""
    in_dir = tmp_path / "photos"
    out_dir = tmp_path / "cropped"
    in_dir.mkdir()

    img = Image.new("RGB", (600, 400), color="orange")
    img.save(in_dir / "profile.jpg")

    ret = main([str(in_dir), "-o", str(out_dir), "-a", "1:1", "-v"])
    assert ret == 0
    assert (out_dir / "profile_crop.jpg").exists()

    with Image.open(out_dir / "profile_crop.jpg") as cropped:
        assert cropped.size == (400, 400)

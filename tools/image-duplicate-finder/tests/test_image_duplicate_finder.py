"""Unit tests for image_duplicate_finder module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_duplicate_finder import (  # noqa: E402
    compute_dhash,
    find_duplicates,
    hamming_distance,
    main,
)


def test_hamming_distance() -> None:
    """Test hamming distance calculation between hashes."""
    assert hamming_distance(0b1010, 0b1010) == 0
    assert hamming_distance(0b1010, 0b1011) == 1
    assert hamming_distance(0b0000, 0b1111) == 4


def test_compute_dhash(tmp_path: Path) -> None:
    """Test computing difference hash for an image."""
    img_path = tmp_path / "test.png"
    img = Image.new("RGB", (64, 64), color="blue")
    img.save(img_path)

    dhash = compute_dhash(img_path)
    assert dhash is not None
    assert isinstance(dhash, int)


def test_find_duplicates(tmp_path: Path) -> None:
    """Test detecting duplicate images in a folder."""
    img1 = tmp_path / "img1.jpg"
    img2 = tmp_path / "img2.jpg"
    img3 = tmp_path / "img3.jpg"

    # Create two identical images and one different image
    Image.new("RGB", (100, 100), color="red").save(img1)
    Image.new("RGB", (100, 100), color="red").save(img2)

    # Gradient image for distinct hash
    other = Image.new("RGB", (100, 100), color="white")
    for x in range(50):
        for y in range(100):
            other.putpixel((x, y), (0, 0, 0))
    other.save(img3)

    groups = find_duplicates(tmp_path, threshold=2)
    assert len(groups) >= 1
    paths_in_group = [item["path"] for item in groups[0]]
    assert str(img1) in paths_in_group and str(img2) in paths_in_group


def test_cli_json_output(tmp_path: Path) -> None:
    """Test CLI JSON execution output format."""
    img1 = tmp_path / "a.png"
    img2 = tmp_path / "b.png"

    Image.new("RGB", (50, 50), color="black").save(img1)
    Image.new("RGB", (50, 50), color="black").save(img2)

    ret = main([str(tmp_path), "-f", "json", "-v"])
    assert ret == 0

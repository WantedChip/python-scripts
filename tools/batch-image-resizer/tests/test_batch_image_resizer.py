"""Unit tests for batch_image_resizer module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from batch_image_resizer import (  # noqa: E402
    calculate_target_dimensions,
    main,
    resize_image,
)


def test_calculate_target_dimensions() -> None:
    """Test dimension scaling and aspect ratio math."""
    # Scale factor
    assert calculate_target_dimensions(1000, 500, scale=0.5) == (500, 250)

    # Max dim
    assert calculate_target_dimensions(1000, 500, max_dim=200) == (200, 100)
    assert calculate_target_dimensions(500, 1000, max_dim=200) == (100, 200)

    # Width only with aspect
    res = calculate_target_dimensions(800, 600, target_width=400, preserve_aspect=True)
    assert res == (400, 300)

    # Width and height with aspect fit
    res_fit = calculate_target_dimensions(
        800, 600, target_width=400, target_height=400, preserve_aspect=True
    )
    assert res_fit == (400, 300)

    # No aspect stretch
    res_stretch = calculate_target_dimensions(
        800, 600, target_width=400, target_height=400, preserve_aspect=False
    )
    assert res_stretch == (400, 400)


def test_resize_image_file(tmp_path: Path) -> None:
    """Test single image file resizing."""
    src_file = tmp_path / "test.png"
    dst_file = tmp_path / "out.png"

    img = Image.new("RGB", (400, 200), color="blue")
    img.save(src_file)

    res = resize_image(src_file, dst_file, target_width=200, preserve_aspect=True)
    assert res is True
    assert dst_file.exists()

    with Image.open(dst_file) as resized:
        assert resized.size == (200, 100)


def test_cli_folder(tmp_path: Path) -> None:
    """Test CLI batch directory processing."""
    in_dir = tmp_path / "images"
    out_dir = tmp_path / "resized"
    in_dir.mkdir()

    for i in range(2):
        im = Image.new("RGB", (600, 400), color="red")
        im.save(in_dir / f"img_{i}.jpg")

    ret = main([str(in_dir), "-o", str(out_dir), "-m", "300", "-v"])
    assert ret == 0
    assert (out_dir / "img_0.jpg").exists()

    with Image.open(out_dir / "img_0.jpg") as resized:
        assert resized.size == (300, 200)


def test_cli_dry_run(tmp_path: Path) -> None:
    """Test CLI dry-run preview mode."""
    src_file = tmp_path / "test.jpg"
    img = Image.new("RGB", (500, 500), color="green")
    img.save(src_file)

    ret = main([str(src_file), "-s", "0.5", "--dry-run"])
    assert ret == 0

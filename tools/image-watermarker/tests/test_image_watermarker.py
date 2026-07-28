"""Unit tests for image_watermarker module."""

import sys
from pathlib import Path

from PIL import Image

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from image_watermarker import (  # noqa: E402
    apply_watermark,
    calculate_watermark_position,
    main,
)


def test_calculate_watermark_position() -> None:
    """Test positioning math for watermark alignments."""
    pos1 = calculate_watermark_position((500, 500), (100, 50), "top-left", 10)
    assert pos1 == (10, 10)
    pos2 = calculate_watermark_position((500, 500), (100, 50), "top-right", 10)
    assert pos2 == (390, 10)
    pos3 = calculate_watermark_position((500, 500), (100, 50), "bottom-left", 10)
    assert pos3 == (10, 440)
    pos4 = calculate_watermark_position((500, 500), (100, 50), "center", 0)
    assert pos4 == (200, 225)
    pos5 = calculate_watermark_position((500, 500), (100, 50), "bottom-right", 10)
    assert pos5 == (390, 440)


def test_apply_text_watermark(tmp_path: Path) -> None:
    """Test text watermark creation and output file generation."""
    src = tmp_path / "photo.jpg"
    dst = tmp_path / "wm_photo.jpg"

    base = Image.new("RGB", (400, 400), color="blue")
    base.save(src)

    ok = apply_watermark(src, dst, text="CONFIDENTIAL", position="center", opacity=0.8)
    assert ok is True
    assert dst.exists()


def test_apply_tiled_watermark(tmp_path: Path) -> None:
    """Test tiled text and image watermark placement."""
    src = tmp_path / "photo.png"
    logo = tmp_path / "logo.png"
    dst_text = tmp_path / "tiled_text.png"
    dst_logo = tmp_path / "tiled_logo.png"

    base = Image.new("RGBA", (300, 300), color="white")
    base.save(src)

    logo_img = Image.new("RGBA", (40, 40), color="red")
    logo_img.save(logo)

    ok1 = apply_watermark(src, dst_text, text="COPYRIGHT", position="tile")
    assert ok1 is True

    ok2 = apply_watermark(src, dst_logo, watermark_img_path=logo, position="tile")
    assert ok2 is True


def test_cli_directory(tmp_path: Path) -> None:
    """Test CLI batch directory processing."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    img = Image.new("RGB", (200, 200), color="green")
    img.save(in_dir / "pic.jpg")

    ret = main(
        [str(in_dir), "-o", str(out_dir), "-t", "SAMPLE", "-p", "bottom-right", "-v"]
    )
    assert ret == 0
    assert (out_dir / "pic_wm.jpg").exists()


def test_cli_missing_watermark_spec() -> None:
    """Test CLI error code when neither text nor logo is provided."""
    ret = main(["sample.jpg"])
    assert ret == 1

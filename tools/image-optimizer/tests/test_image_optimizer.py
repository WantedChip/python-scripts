"""Tests for Image Optimization Pipeline."""

# pylint: disable=too-few-public-methods


import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=import-error, wrong-import-position
import image_optimizer  # noqa: E402


def create_test_image(
    path: Path,
    size: tuple[int, int] = (10, 10),
    fmt: str = "JPEG",
    include_exif: bool = False,
) -> None:
    """Create a dummy test image on disk."""
    img = Image.new("RGB", size, color="red")
    save_args = {}
    if include_exif:
        exif = img.getexif()
        exif[274] = 3  # Orientation: 180 degrees
        save_args["exif"] = exif.tobytes()

    img.save(path, format=fmt, **save_args)


def test_is_matching() -> None:
    """Test fnmatch filtering helper."""
    assert image_optimizer.is_matching("image.png", "*.png", "")
    assert not image_optimizer.is_matching("image.png", "*.jpg", "")
    assert not image_optimizer.is_matching("image.png", "*.png", "*image*")
    assert image_optimizer.is_matching("image.png", "", "")


def test_resize_image() -> None:
    """Test image resizing logic."""
    img = Image.new("RGB", (100, 200), color="blue")

    # Scale factor
    res = image_optimizer.resize_image(img, None, None, 0.5)
    assert res.size == (50, 100)

    # Exact dimensions
    res = image_optimizer.resize_image(img, 80, 80, None)
    assert res.size == (80, 80)

    # Width preserving aspect ratio
    res = image_optimizer.resize_image(img, 50, None, None)
    assert res.size == (50, 100)

    # Height preserving aspect ratio
    res = image_optimizer.resize_image(img, None, 50, None)
    assert res.size == (25, 50)


def test_metadata_retention(tmp_path: Path) -> None:
    """Test EXIF metadata processing rules."""
    img_path = tmp_path / "src.jpg"
    create_test_image(img_path, include_exif=True)

    with Image.open(img_path) as img:
        # Strip EXIF
        exif_strip = image_optimizer.get_exif_bytes(img, "strip")
        assert exif_strip is None

        # Keep EXIF
        exif_keep = image_optimizer.get_exif_bytes(img, "keep")
        assert exif_keep is not None

        # Keep orientation only
        exif_ori = image_optimizer.get_exif_bytes(img, "orientation")
        assert exif_ori is not None


def test_process_image(tmp_path: Path) -> None:
    """Test single image process flow."""
    src = tmp_path / "src.jpg"
    dest = tmp_path / "dest.png"
    create_test_image(src, size=(20, 20))

    class MockArgs:
        """Mock args namespace."""

        width = 10
        height = None
        scale = None
        metadata = "strip"
        quality = 85
        png_optimize = 6
        dry_run = False

    args = MockArgs()
    success = image_optimizer.process_image(src, dest, args)

    assert success
    assert dest.exists()
    with Image.open(dest) as img:
        assert img.size == (10, 10)
        assert img.format == "PNG"


def test_run_pipeline_recursively(tmp_path: Path) -> None:
    """Test recursive directory walk and output mappings."""
    src_dir = tmp_path / "input"
    src_dir.mkdir()
    sub_dir = src_dir / "sub"
    sub_dir.mkdir()
    out_dir = tmp_path / "output"

    img1 = src_dir / "img1.jpg"
    img2 = sub_dir / "img2.png"
    create_test_image(img1)
    create_test_image(img2, fmt="PNG")

    class MockArgs:
        """Mock args namespace."""

        input = str(src_dir)
        output_dir = str(out_dir)
        in_place = False
        suffix = ""
        width = None
        height = None
        scale = 0.5
        format = "WEBP"
        quality = 80
        png_optimize = 6
        metadata = "strip"
        include = ""
        exclude = ""
        min_size = None
        max_size = None
        dry_run = False
        verbose = False

    args = MockArgs()
    image_optimizer.run_pipeline(args)

    assert (out_dir / "img1.webp").exists()
    assert (out_dir / "sub" / "img2.webp").exists()


def test_run_pipeline_single_file(tmp_path: Path) -> None:
    """Test running on a single file."""
    src = tmp_path / "img.png"
    out_dir = tmp_path / "out"
    create_test_image(src, fmt="PNG")

    class MockArgs:
        """Mock args."""

        input = str(src)
        output_dir = str(out_dir)
        in_place = False
        suffix = "_opt"
        width = None
        height = None
        scale = None
        format = "PNG"
        quality = 90
        png_optimize = 6
        metadata = "strip"
        include = ""
        exclude = ""
        min_size = None
        max_size = None
        dry_run = False
        verbose = False

    args = MockArgs()
    image_optimizer.run_pipeline(args)

    assert (out_dir / "img_opt.png").exists()


def test_pipeline_prevents_overwrite(tmp_path: Path) -> None:
    """Test pipeline skips execution if target output equals source file

    and not in-place.
    """

    src = tmp_path / "img.png"
    create_test_image(src, fmt="PNG")

    class MockArgs:
        """Mock args."""

        input = str(src)
        output_dir = None
        in_place = False
        suffix = ""
        width = 5
        height = 5
        scale = None
        format = None
        quality = 90
        png_optimize = 6
        metadata = "strip"
        include = ""
        exclude = ""
        min_size = None
        max_size = None
        dry_run = False
        verbose = False

    args = MockArgs()
    image_optimizer.run_pipeline(args)

    # Image should not be resized since it was skipped
    with Image.open(src) as img:
        assert img.size == (10, 10)


def test_main_cli_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test argparse entry-point."""
    src = tmp_path / "img.jpg"
    out_dir = tmp_path / "out"
    create_test_image(src)

    args = [
        "image_optimizer.py",
        "-i",
        str(src),
        "-o",
        str(out_dir),
        "--scale",
        "0.8",
        "-f",
        "WEBP",
    ]
    monkeypatch.setattr(sys, "argv", args)

    image_optimizer.main()
    assert (out_dir / "img.webp").exists()


def test_main_cli_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI error exit path."""
    args = [
        "image_optimizer.py",
        "-i",
        "nonexistent_image_dir",
    ]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(SystemExit) as exc:
        image_optimizer.main()
    assert exc.value.code == 1

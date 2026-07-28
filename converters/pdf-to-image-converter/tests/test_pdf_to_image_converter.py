"""Unit test suite for pdf_to_image_converter module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_to_image_converter import (  # noqa: E402
    convert_pdf_to_images,
    main,
    parse_page_ranges,
    render_fallback_page_image,
)


def create_dummy_pdf(
    output_path: Path, num_pages: int = 3, password: str | None = None
) -> None:
    """Helper to generate a dummy PDF file with blank pages."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    if password:
        writer.encrypt(password)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f_out:
        writer.write(f_out)


def test_parse_page_ranges() -> None:
    """Test parsing range string into 0-indexed page set."""
    res = parse_page_ranges("1-2,4,invalid,10-2", 5)
    assert res == {0, 1, 3}


def test_render_fallback_page_image() -> None:
    """Test creating synthetic page snapshot image."""
    img = render_fallback_page_image(1, "Hello World\nLine 2")
    assert img.size == (800, 1000)


def test_convert_pdf_to_images(tmp_path: Path) -> None:
    """Test converting PDF pages to PNG image files."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path, 2)

    out_dir = tmp_path / "img_out"
    images = convert_pdf_to_images(pdf_path, out_dir, img_format="png", range_str="1-2")
    assert len(images) == 2
    for img in images:
        assert img.exists()


def test_convert_pdf_encrypted(tmp_path: Path) -> None:
    """Test handling encrypted PDF without password."""
    pdf_path = tmp_path / "secret.pdf"
    create_dummy_pdf(pdf_path, 2, password="secret")

    out_dir = tmp_path / "secret_out"
    assert len(convert_pdf_to_images(pdf_path, out_dir)) == 0


def test_main_cli(tmp_path: Path) -> None:
    """Test main CLI entrypoint execution."""
    pdf_path = tmp_path / "doc.pdf"
    create_dummy_pdf(pdf_path, 2)

    out_dir = tmp_path / "cli_imgs"
    ret = main([str(pdf_path), "-o", str(out_dir), "-f", "jpeg", "-v"])
    assert ret == 0

    assert main([str(tmp_path / "non_existent.pdf")]) == 1

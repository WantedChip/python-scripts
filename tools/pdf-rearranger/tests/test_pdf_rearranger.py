"""Unit test suite for pdf_rearranger module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_rearranger import main, parse_page_indices, rearrange_pdf_pages  # noqa: E402


def create_dummy_pdf(
    output_path: Path, num_pages: int = 4, password: str | None = None
) -> None:
    """Helper to generate a dummy PDF file."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    if password:
        writer.encrypt(password)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f_out:
        writer.write(f_out)


def test_parse_page_indices() -> None:
    """Test parsing page index selection strings."""
    assert parse_page_indices("3,1-2,4", 5) == [2, 0, 1, 3]


def test_rearrange_pdf_pages(tmp_path: Path) -> None:
    """Test reordering, rotating, and deleting PDF pages."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path, 5)

    out_pdf = tmp_path / "rearranged.pdf"
    success = rearrange_pdf_pages(
        pdf_path,
        out_pdf,
        reorder_str="3,1,2",
        rotate_angle=90,
        rotate_pages_str="1",
        delete_str="4",
    )
    assert success is True
    assert out_pdf.exists()


def test_main_cli(tmp_path: Path) -> None:
    """Test main CLI entrypoint execution."""
    pdf_path = tmp_path / "doc.pdf"
    create_dummy_pdf(pdf_path, 4)

    out_pdf = tmp_path / "cli_out.pdf"
    assert (
        main([str(pdf_path), "-r", "2,1,3", "-d", "4", "-o", str(out_pdf), "-v"]) == 0
    )
    assert out_pdf.exists()

    assert main([str(tmp_path / "non_existent.pdf")]) == 1

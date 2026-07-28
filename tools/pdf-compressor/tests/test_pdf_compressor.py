"""Unit test suite for pdf_compressor module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_compressor import compress_pdf_file, main  # noqa: E402


def create_dummy_pdf(
    output_path: Path, num_pages: int = 3, password: str | None = None
) -> None:
    """Helper to generate a dummy PDF file with N blank pages."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    if password:
        writer.encrypt(password)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f_out:
        writer.write(f_out)


def test_compress_pdf_file_success(tmp_path: Path) -> None:
    """Test compressing valid PDF file."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path, 4)

    out_pdf = tmp_path / "compressed_sample.pdf"
    info = compress_pdf_file(pdf_path, out_pdf)
    assert info["status"] == "ok"
    assert out_pdf.exists()
    assert info["compressed_size"] > 0


def test_main_cli_file_and_directory(tmp_path: Path) -> None:
    """Test main CLI entrypoint with single file and directory input."""
    sub_dir = tmp_path / "pdf_dir"
    pdf1 = sub_dir / "p1.pdf"
    pdf2 = sub_dir / "p2.pdf"
    create_dummy_pdf(pdf1, 2)
    create_dummy_pdf(pdf2, 2)

    out_pdf = tmp_path / "single_out.pdf"
    assert main([str(pdf1), "-o", str(out_pdf), "-v"]) == 0
    assert out_pdf.exists()

    out_dir = tmp_path / "compressed_dir"
    assert main([str(sub_dir), "-o", str(out_dir)]) == 0

    assert main([str(tmp_path / "non_existent.pdf")]) == 1

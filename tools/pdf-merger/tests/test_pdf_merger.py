"""Unit test suite for pdf_merger module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_merger import (  # noqa: E402
    main,
    merge_pdf_files,
    parse_page_range,
    parse_pdf_input_spec,
)


def create_dummy_pdf(output_path: Path, num_pages: int = 2) -> None:
    """Helper to generate a dummy PDF file with N blank pages."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f_out:
        writer.write(f_out)


def test_parse_pdf_input_spec() -> None:
    """Test parsing file specs with page ranges."""
    p, r = parse_pdf_input_spec("doc.pdf:1-5")
    assert p == Path("doc.pdf")
    assert r == "1-5"


def test_parse_page_range() -> None:
    """Test page range conversion."""
    assert parse_page_range("1-5", 10) == (0, 5)
    assert parse_page_range("3", 10) == (2, 3)
    assert parse_page_range("invalid", 10) is None


def test_merge_pdf_files_success(tmp_path: Path) -> None:
    """Test merging valid PDF files."""
    pdf1 = tmp_path / "pdf1.pdf"
    pdf2 = tmp_path / "pdf2.pdf"
    out_pdf = tmp_path / "merged_out.pdf"

    create_dummy_pdf(pdf1, 2)
    create_dummy_pdf(pdf2, 3)

    success = merge_pdf_files([str(pdf1), str(pdf2)], out_pdf)
    assert success is True
    assert out_pdf.exists()


def test_merge_pdf_files_missing_source(tmp_path: Path) -> None:
    """Test merging with a missing source PDF."""
    missing = tmp_path / "missing.pdf"
    out_pdf = tmp_path / "merged_out.pdf"

    assert merge_pdf_files([str(missing)], out_pdf) is False


def test_main_cli_and_directory(tmp_path: Path) -> None:
    """Test main CLI entrypoint with directory inputs."""
    sub_dir = tmp_path / "pdf_folder"
    pdf1 = sub_dir / "a.pdf"
    pdf2 = sub_dir / "b.pdf"
    create_dummy_pdf(pdf1, 1)
    create_dummy_pdf(pdf2, 1)

    out_pdf = tmp_path / "output.pdf"
    ret = main([str(sub_dir), "-o", str(out_pdf), "-v"])
    assert ret == 0
    assert out_pdf.exists()

    assert main([str(tmp_path / "non_existent_folder")]) == 1

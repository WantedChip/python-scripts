"""Unit test suite for pdf_page_splitter module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_page_splitter import main, parse_page_ranges, split_pdf_file  # noqa: E402


def create_dummy_pdf(output_path: Path, num_pages: int = 5) -> None:
    """Helper to generate a dummy PDF file with N blank pages."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f_out:
        writer.write(f_out)


def test_parse_page_ranges() -> None:
    """Test parsing page ranges string into 0-indexed page set."""
    res = parse_page_ranges("1-3,5", 10)
    assert res == {0, 1, 2, 4}


def test_split_pdf_all_pages(tmp_path: Path) -> None:
    """Test splitting every page of PDF into separate files."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path, 3)

    out_dir = tmp_path / "split_out"
    files = split_pdf_file(pdf_path, out_dir)
    assert len(files) == 3
    for f in files:
        assert f.exists()


def test_split_pdf_chunks(tmp_path: Path) -> None:
    """Test splitting PDF into chunks of N pages."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path, 5)

    out_dir = tmp_path / "chunk_out"
    files = split_pdf_file(pdf_path, out_dir, chunk_size=2)
    assert len(files) == 3


def test_split_pdf_ranges(tmp_path: Path) -> None:
    """Test splitting PDF using specific page range string."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path, 5)

    out_dir = tmp_path / "range_out"
    files = split_pdf_file(pdf_path, out_dir, ranges_str="1-2,4")
    assert len(files) == 1
    assert files[0].exists()


def test_main_cli_success(tmp_path: Path) -> None:
    """Test main CLI entrypoint execution."""
    pdf_path = tmp_path / "doc.pdf"
    create_dummy_pdf(pdf_path, 4)

    out_dir = tmp_path / "cli_out"
    ret = main([str(pdf_path), "-o", str(out_dir), "-c", "2", "-v"])
    assert ret == 0

    assert main([str(tmp_path / "non_existent.pdf")]) == 1

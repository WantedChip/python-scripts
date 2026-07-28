"""Unit test suite for pdf_page_counter module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_page_counter import count_pdf_pages, main, scan_pdf_directory  # noqa: E402


def create_dummy_pdf(
    output_path: Path, num_pages: int = 2, password: str | None = None
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


def test_count_pdf_pages(tmp_path: Path) -> None:
    """Test page counting on single PDF."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path, 3)

    info = count_pdf_pages(pdf_path)
    assert info["pages"] == 3
    assert info["status"] == "ok"


def test_scan_pdf_directory_and_main(tmp_path: Path) -> None:
    """Test directory scanning and main CLI invocation."""
    sub_dir = tmp_path / "pdfs"
    p1 = sub_dir / "doc1.pdf"
    p2 = sub_dir / "doc2.pdf"
    create_dummy_pdf(p1, 2)
    create_dummy_pdf(p2, 4)

    results, total_pages, total_bytes = scan_pdf_directory(sub_dir)
    assert len(results) == 2
    assert total_pages == 6
    assert total_bytes > 0

    json_out = tmp_path / "out.json"
    csv_out = tmp_path / "out.csv"

    assert main([str(sub_dir), "-o", str(json_out), "-f", "json", "-v"]) == 0
    assert json_out.exists()

    assert main([str(sub_dir), "-o", str(csv_out), "-f", "csv"]) == 0
    assert csv_out.exists()

    assert main([str(sub_dir), "-f", "table"]) == 0
    assert main([str(tmp_path / "non_existent")]) == 1

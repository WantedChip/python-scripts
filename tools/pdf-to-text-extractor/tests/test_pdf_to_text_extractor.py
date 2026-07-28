"""Unit test suite for pdf_to_text_extractor module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_to_text_extractor import (  # noqa: E402
    extract_text_from_pdf,
    main,
    parse_page_range,
)


def create_dummy_pdf(output_path: Path, num_pages: int = 3) -> None:
    """Helper to generate a dummy PDF file with N blank pages."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f_out:
        writer.write(f_out)


def test_parse_page_range() -> None:
    """Test parsing page range string into 0-indexed page set."""
    res = parse_page_range("1-3,5", 10)
    assert res == {0, 1, 2, 4}


def test_extract_text_from_pdf(tmp_path: Path) -> None:
    """Test extracting text from dummy PDF."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path, 2)

    res = extract_text_from_pdf(pdf_path, range_str="1")
    assert res["status"] == "ok"
    assert res["total_pages"] == 2
    assert res["extracted_pages"] == 1


def test_main_cli_file_and_json(tmp_path: Path) -> None:
    """Test main CLI entrypoint execution."""
    sub_dir = tmp_path / "pdf_dir"
    pdf1 = sub_dir / "p1.pdf"
    pdf2 = sub_dir / "p2.pdf"
    create_dummy_pdf(pdf1, 2)
    create_dummy_pdf(pdf2, 2)

    txt_out = tmp_path / "out.txt"
    json_out = tmp_path / "out.json"

    assert main([str(pdf1), "-o", str(txt_out), "-v"]) == 0
    assert txt_out.exists()

    assert main([str(pdf1), "-o", str(json_out), "-f", "json"]) == 0
    assert json_out.exists()

    # Test folder input stdout and directory output
    assert main([str(sub_dir), "-f", "txt"]) == 0
    assert main([str(sub_dir), "-f", "json"]) == 0
    out_dir = tmp_path / "out_dir"
    assert main([str(sub_dir), "-o", str(out_dir), "-f", "txt"]) == 0
    assert main([str(sub_dir), "-o", str(out_dir), "-f", "json"]) == 0

    assert main([str(tmp_path / "non_existent.pdf")]) == 1

"""Unit test suite for pdf_toc_generator module."""

import json
import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_toc_generator import (  # noqa: E402
    add_toc_bookmarks,
    detect_headings_in_pdf,
    main,
)


def create_dummy_pdf(
    output_path: Path, num_pages: int = 3, password: str | None = None
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


def test_detect_headings_in_pdf(tmp_path: Path) -> None:
    """Test detecting headings in PDF."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path)

    entries = detect_headings_in_pdf(pdf_path)
    assert isinstance(entries, list)


def test_add_toc_bookmarks(tmp_path: Path) -> None:
    """Test embedding TOC bookmarks into PDF."""
    pdf_path = tmp_path / "doc.pdf"
    create_dummy_pdf(pdf_path, 3)

    out_path = tmp_path / "doc_toc.pdf"
    toc_data = [
        {"title": "Section 1", "page": 1},
        {"title": "Section 2", "page": 2},
    ]
    success = add_toc_bookmarks(pdf_path, out_path, toc_data)
    assert success is True
    assert out_path.exists()


def test_main_cli(tmp_path: Path) -> None:
    """Test main CLI entrypoint execution."""
    pdf_path = tmp_path / "doc.pdf"
    create_dummy_pdf(pdf_path, 3)

    cfg_file = tmp_path / "toc.json"
    cfg_file.write_text(
        json.dumps([{"title": "Chapter 1", "page": 1}]), encoding="utf-8"
    )

    out_pdf = tmp_path / "cli_toc.pdf"

    assert main([str(pdf_path), "-c", str(cfg_file), "-o", str(out_pdf), "-v"]) == 0
    assert out_pdf.exists()

    assert main([str(pdf_path)]) == 0
    assert main([str(tmp_path / "non_existent.pdf")]) == 1

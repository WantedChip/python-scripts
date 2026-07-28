"""Unit test suite for pdf_metadata_editor module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_metadata_editor import (  # noqa: E402
    main,
    read_pdf_metadata,
    update_pdf_metadata,
)


def create_dummy_pdf(
    output_path: Path, title: str = "Test Title", author: str = "Test Author"
) -> None:
    """Helper to generate a dummy PDF file with metadata."""
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_metadata({"/Title": title, "/Author": author})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f_out:
        writer.write(f_out)


def test_read_pdf_metadata(tmp_path: Path) -> None:
    """Test reading PDF metadata."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path, title="My Book", author="John Smith")

    meta = read_pdf_metadata(pdf_path)
    assert meta["status"] == "ok"
    assert meta["title"] == "My Book"
    assert meta["author"] == "John Smith"


def test_update_pdf_metadata(tmp_path: Path) -> None:
    """Test updating PDF metadata."""
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path)

    out_path = tmp_path / "updated.pdf"
    new_tags = {"title": "Updated Title", "author": "New Author"}
    success = update_pdf_metadata(pdf_path, out_path, new_tags)
    assert success is True

    updated_meta = read_pdf_metadata(out_path)
    assert updated_meta["title"] == "Updated Title"
    assert updated_meta["author"] == "New Author"


def test_main_cli_view_and_edit(tmp_path: Path) -> None:
    """Test main CLI entrypoint execution in view and edit modes."""
    pdf_path = tmp_path / "doc.pdf"
    create_dummy_pdf(pdf_path, title="Initial")

    # View mode
    assert main([str(pdf_path), "-v", "-f", "table"]) == 0
    assert main([str(pdf_path), "-f", "json"]) == 0

    # Edit mode out file
    out_pdf = tmp_path / "mod.pdf"
    assert main([str(pdf_path), "--title", "Changed", "-o", str(out_pdf)]) == 0
    assert out_pdf.exists()

    # Edit mode in-place
    assert main([str(pdf_path), "--title", "Inplace Title", "--in-place"]) == 0

    assert main([str(tmp_path / "non_existent.pdf")]) == 1

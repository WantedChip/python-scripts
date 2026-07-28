"""Unit test suite for document_text_search module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from document_text_search import main, search_directory  # noqa: E402


def create_dummy_files(tmp_path: Path) -> None:
    """Helper to generate text and PDF files for search testing."""
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text(
        "Line 1: Hello World\nLine 2: Target keyword inside\nLine 3: End",
        encoding="utf-8",
    )

    pdf_path = tmp_path / "doc.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with open(pdf_path, "wb") as f_out:
        writer.write(f_out)


def test_search_directory(tmp_path: Path) -> None:
    """Test searching directory containing text and PDF files."""
    create_dummy_files(tmp_path)

    results = search_directory(tmp_path, "keyword")
    assert len(results) >= 1
    assert results[0]["filename"] == "notes.txt"


def test_main_cli_modes(tmp_path: Path) -> None:
    """Test main CLI entrypoint in table, json, csv, and report export modes."""
    create_dummy_files(tmp_path)

    json_out = tmp_path / "out.json"
    csv_out = tmp_path / "out.csv"

    assert (
        main([str(tmp_path), "keyword", "-o", str(json_out), "-f", "json", "-v"]) == 0
    )
    assert json_out.exists()

    assert main([str(tmp_path), "keyword", "-o", str(csv_out), "-f", "csv"]) == 0
    assert csv_out.exists()

    assert main([str(tmp_path), "keyword", "-f", "table"]) == 0
    assert main([str(tmp_path / "non_existent"), "query"]) == 1

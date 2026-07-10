"""Tests for PDF Batch Toolkit."""

import sys
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).parent.parent))

import pdf_toolkit  # noqa: E402  # pylint: disable=import-error, wrong-import-position


def create_dummy_pdf(
    path: Path, pages_count: int = 3, encrypted: bool = False, password: str = "pass"
) -> None:
    """Create a dummy PDF file for testing."""
    writer = PdfWriter()
    for _ in range(pages_count):
        writer.add_blank_page(width=72, height=72)
    if encrypted:
        writer.encrypt(password)
    with open(path, "wb") as f:
        writer.write(f)


def test_parse_page_range() -> None:
    """Test parse_page_range with various inputs."""
    assert pdf_toolkit.parse_page_range("1-3", 5) == {0, 1, 2}
    assert pdf_toolkit.parse_page_range("1,3,5", 5) == {0, 2, 4}
    assert pdf_toolkit.parse_page_range("2-", 5) == {1, 2, 3, 4}
    assert pdf_toolkit.parse_page_range("-3", 5) == {0, 1, 2}
    assert pdf_toolkit.parse_page_range("1-3,5,2-2", 5) == {0, 1, 2, 4}
    assert pdf_toolkit.parse_page_range("10-12", 5) == set()
    assert pdf_toolkit.parse_page_range("  ", 5) == set()

    with pytest.raises(ValueError):
        pdf_toolkit.parse_page_range("1-2-3", 5)
    with pytest.raises(ValueError):
        pdf_toolkit.parse_page_range("abc", 5)
    with pytest.raises(ValueError):
        pdf_toolkit.parse_page_range("0", 5)


def test_handle_merge(tmp_path: Path) -> None:
    """Test merging multiple PDFs."""
    pdf1 = tmp_path / "pdf1.pdf"
    pdf2 = tmp_path / "pdf2.pdf"
    out = tmp_path / "merged.pdf"

    create_dummy_pdf(pdf1, 2)
    create_dummy_pdf(pdf2, 3)

    pdf_toolkit.handle_merge([pdf1, pdf2], out, "")

    assert out.exists()
    reader = PdfReader(str(out))
    assert len(reader.pages) == 5


def test_handle_split_all(tmp_path: Path) -> None:
    """Test splitting all pages."""
    pdf = tmp_path / "input.pdf"
    out_dir = tmp_path / "output_split"

    create_dummy_pdf(pdf, 3)

    pdf_toolkit.handle_split(pdf, out_dir, "", "")

    assert (out_dir / "input_page_1.pdf").exists()
    assert (out_dir / "input_page_2.pdf").exists()
    assert (out_dir / "input_page_3.pdf").exists()

    reader = PdfReader(str(out_dir / "input_page_1.pdf"))
    assert len(reader.pages) == 1


def test_handle_split_ranges(tmp_path: Path) -> None:
    """Test splitting specific ranges."""
    pdf = tmp_path / "input.pdf"
    out_dir = tmp_path / "output_ranges"

    create_dummy_pdf(pdf, 5)

    pdf_toolkit.handle_split(pdf, out_dir, "1-2,4", "")

    out_file = out_dir / "input_split.pdf"
    assert out_file.exists()
    reader = PdfReader(str(out_file))
    assert len(reader.pages) == 3


def test_handle_rotate(tmp_path: Path) -> None:
    """Test page rotation."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "rotated.pdf"

    create_dummy_pdf(pdf, 2)

    pdf_toolkit.handle_rotate(pdf, out, 90, "1", "")

    assert out.exists()
    reader = PdfReader(str(out))
    # PyPDF2 pages are rotated
    assert reader.pages[0].rotation == 90  # pylint: disable=no-member
    assert reader.pages[1].rotation == 0  # pylint: disable=no-member


def test_handle_extract(tmp_path: Path) -> None:
    """Test page extraction."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "extracted.pdf"

    create_dummy_pdf(pdf, 5)

    pdf_toolkit.handle_extract(pdf, out, "2-4", "")

    assert out.exists()
    reader = PdfReader(str(out))
    assert len(reader.pages) == 3


def test_handle_compress(tmp_path: Path) -> None:
    """Test content stream compression."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "compressed.pdf"

    create_dummy_pdf(pdf, 3)

    pdf_toolkit.handle_compress(pdf, out, "")

    assert out.exists()
    reader = PdfReader(str(out))
    assert len(reader.pages) == 3


def test_handle_rename(tmp_path: Path) -> None:
    """Test bulk renaming."""
    pdf_dir = tmp_path / "rename_dir"
    pdf_dir.mkdir()

    pdf1 = pdf_dir / "file_one.pdf"
    pdf2 = pdf_dir / "file_two.pdf"

    create_dummy_pdf(pdf1, 1)
    create_dummy_pdf(pdf2, 1)

    # Dry run
    pdf_toolkit.handle_rename(pdf_dir, "newname", False, True, True)
    assert pdf1.exists()
    assert pdf2.exists()

    # Actual rename
    pdf_toolkit.handle_rename(pdf_dir, "newname", False, True, False)
    assert not pdf1.exists()
    assert not pdf2.exists()

    assert (pdf_dir / "newname_001.pdf").exists()
    assert (pdf_dir / "newname_002.pdf").exists()


def test_rename_with_date(tmp_path: Path) -> None:
    """Test bulk renaming with date prefix."""
    pdf_dir = tmp_path / "rename_dir"
    pdf_dir.mkdir()
    pdf = pdf_dir / "file.pdf"
    create_dummy_pdf(pdf, 1)

    pdf_toolkit.handle_rename(pdf_dir, "", True, False, False)

    # File should have prefix date
    files = list(pdf_dir.glob("*.pdf"))
    assert len(files) == 1
    assert files[0].name != "file.pdf"
    assert len(files[0].name.split("_")[0]) == 10  # YYYY-MM-DD


def test_encrypted_pdf(tmp_path: Path) -> None:
    """Test decryption workflow for encrypted PDF."""
    pdf = tmp_path / "encrypted.pdf"
    out = tmp_path / "decrypted.pdf"

    create_dummy_pdf(pdf, 2, encrypted=True, password="secretpassword")

    # Should raise error without password
    with pytest.raises(ValueError, match="PDF is encrypted"):
        pdf_toolkit.handle_extract(pdf, out, "1", "")

    # Should raise error with wrong password
    with pytest.raises(ValueError, match="Decryption failed"):
        pdf_toolkit.handle_extract(pdf, out, "1", "wrongpass")

    # Should succeed with correct password
    pdf_toolkit.handle_extract(pdf, out, "1", "secretpassword")
    assert out.exists()
    reader = PdfReader(str(out))
    assert len(reader.pages) == 1


def test_setup_logging() -> None:
    """Test logging setup."""
    pdf_toolkit.setup_logging(True)
    assert pdf_toolkit.logger.level == 10  # DEBUG
    pdf_toolkit.setup_logging(False)
    assert pdf_toolkit.logger.level == 20  # INFO


def test_main_cli_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main function CLI arg parsing."""
    pdf1 = tmp_path / "pdf1.pdf"
    pdf2 = tmp_path / "pdf2.pdf"
    out = tmp_path / "merged.pdf"
    create_dummy_pdf(pdf1, 1)
    create_dummy_pdf(pdf2, 1)

    # Mock sys.argv
    args = [
        "pdf_toolkit.py",
        "merge",
        "-i",
        str(pdf1),
        str(pdf2),
        "-o",
        str(out),
    ]
    monkeypatch.setattr(sys, "argv", args)

    pdf_toolkit.main()
    assert out.exists()


def test_main_cli_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI exit on error."""
    # Pass non-existent file to compress
    args = [
        "pdf_toolkit.py",
        "compress",
        "-i",
        "nonexistent.pdf",
        "-o",
        "out.pdf",
    ]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(SystemExit) as exc:
        pdf_toolkit.main()
    assert exc.value.code == 1

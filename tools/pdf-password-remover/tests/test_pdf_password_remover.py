"""Unit test suite for pdf_password_remover module."""

import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_password_remover import main, remove_pdf_password  # noqa: E402


def create_dummy_pdf(
    output_path: Path, num_pages: int = 2, password: str | None = None
) -> None:
    """Helper to generate a dummy PDF file with N blank pages and optional password."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    if password:
        writer.encrypt(password)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f_out:
        writer.write(f_out)


def test_remove_pdf_password_unencrypted(tmp_path: Path) -> None:
    """Test removing password from unencrypted PDF."""
    pdf_path = tmp_path / "plain.pdf"
    create_dummy_pdf(pdf_path, 2)

    out_path = tmp_path / "plain_out.pdf"
    success = remove_pdf_password(pdf_path, out_path)
    assert success is True
    assert out_path.exists()


def test_remove_pdf_password_encrypted(tmp_path: Path) -> None:
    """Test removing password from encrypted PDF with password."""
    pdf_path = tmp_path / "secret.pdf"
    create_dummy_pdf(pdf_path, 2, password="mysecretpassword")

    # Missing password should fail
    fail_out = tmp_path / "fail.pdf"
    assert remove_pdf_password(pdf_path, fail_out) is False

    # Incorrect password should fail
    assert remove_pdf_password(pdf_path, fail_out, password="wrong") is False

    # Correct password should succeed
    out_path = tmp_path / "secret_unlocked.pdf"
    success = remove_pdf_password(pdf_path, out_path, password="mysecretpassword")
    assert success is True
    assert out_path.exists()


def test_main_cli(tmp_path: Path) -> None:
    """Test main CLI entrypoint execution."""
    pdf_path = tmp_path / "secret.pdf"
    create_dummy_pdf(pdf_path, 2, password="pass")

    out_path = tmp_path / "unlocked.pdf"
    ret = main([str(pdf_path), "-p", "pass", "-o", str(out_path), "-v"])
    assert ret == 0

    assert main([str(tmp_path / "non_existent.pdf")]) == 1

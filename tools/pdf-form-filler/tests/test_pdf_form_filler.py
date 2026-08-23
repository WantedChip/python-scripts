"""Unit test suite for pdf_form_filler module."""

import json
import sys
from pathlib import Path

from pypdf import PdfWriter

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_form_filler import fill_pdf_form, inspect_form_fields, main  # noqa: E402


def create_dummy_pdf(
    output_path: Path, num_pages: int = 2, password: str | None = None
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


def test_inspect_form_fields(tmp_path: Path) -> None:
    """Test inspecting form fields on blank PDF."""
    pdf_path = tmp_path / "form.pdf"
    create_dummy_pdf(pdf_path)

    res = inspect_form_fields(pdf_path)
    assert res["status"] == "ok"


def test_inspect_encrypted_pdf(tmp_path: Path) -> None:
    """Test inspecting encrypted PDF without password."""
    pdf_path = tmp_path / "secret_form.pdf"
    create_dummy_pdf(pdf_path, password="secret")

    res = inspect_form_fields(pdf_path)
    assert res["status"] == "encrypted_password_required"


def test_fill_pdf_form(tmp_path: Path) -> None:
    """Test filling PDF form with dict values."""
    pdf_path = tmp_path / "form.pdf"
    create_dummy_pdf(pdf_path)

    out_path = tmp_path / "filled.pdf"
    success = fill_pdf_form(pdf_path, out_path, {"First Name": "Alice"})
    assert success is True
    assert out_path.exists()

    # Test encrypted fill fail
    enc_path = tmp_path / "enc.pdf"
    create_dummy_pdf(enc_path, password="pass")
    assert fill_pdf_form(enc_path, out_path, {}) is False


def test_main_cli(tmp_path: Path) -> None:
    """Test main CLI entrypoint execution."""
    pdf_path = tmp_path / "form.pdf"
    create_dummy_pdf(pdf_path)

    json_data = tmp_path / "data.json"
    json_data.write_text(json.dumps({"Name": "Bob"}), encoding="utf-8")

    out_pdf = tmp_path / "out_cli.pdf"

    assert main([str(pdf_path), "--dump-fields"]) == 0
    assert main([str(pdf_path), "-d", str(json_data), "-o", str(out_pdf), "-v"]) == 0
    assert out_pdf.exists()

    # Missing data flag
    assert main([str(pdf_path)]) == 1

    # Missing data file
    assert main([str(pdf_path), "-d", str(tmp_path / "missing.json")]) == 1

    # Non-dict json
    list_json = tmp_path / "array.json"
    list_json.write_text("[1, 2, 3]", encoding="utf-8")
    assert main([str(pdf_path), "-d", str(list_json)]) == 1

    assert main([str(tmp_path / "non_existent.pdf"), "--dump-fields"]) == 1

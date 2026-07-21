import csv
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock pypdf in sys.modules so import works and we can test behavior with and without it
mock_pypdf = MagicMock()
sys.modules["pypdf"] = mock_pypdf

# Add target directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import receipt_normalizer  # noqa: E402


def test_extract_text_txt_success(tmp_path):
    text_file = tmp_path / "receipt.txt"
    text_file.write_text("Hello Receipt", encoding="utf-8")

    content = receipt_normalizer.extract_text(str(text_file))
    assert content == "Hello Receipt"


def test_extract_text_txt_oserror(capsys):
    content = receipt_normalizer.extract_text("nonexistent_file.txt")
    assert content == ""
    captured = capsys.readouterr()
    assert "Error reading text file" in captured.err


def test_extract_text_pdf_no_pypdf(capsys):
    with patch("receipt_normalizer.HAS_PYPDF", False):
        content = receipt_normalizer.extract_text("test.pdf")
        assert content == ""
        captured = capsys.readouterr()
        assert "Skipped PDF parsing" in captured.err


def test_extract_text_pdf_success():
    mock_reader = MagicMock()
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Page 1 Content"
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page 2 Content"
    mock_reader.pages = [mock_page1, mock_page2]

    with patch("receipt_normalizer.HAS_PYPDF", True), patch(
        "pypdf.PdfReader", return_value=mock_reader
    ):
        content = receipt_normalizer.extract_text("test.pdf")
        assert content == "Page 1 Content\nPage 2 Content"


def test_extract_text_pdf_exception(capsys):
    with patch("receipt_normalizer.HAS_PYPDF", True), patch(
        "pypdf.PdfReader", side_effect=OSError("PDF Corrupt")
    ):
        content = receipt_normalizer.extract_text("test.pdf")
        assert content == ""
        captured = capsys.readouterr()
        assert "Error reading PDF" in captured.err


def test_parse_receipt_text_empty():
    res = receipt_normalizer.parse_receipt_text("")
    assert res == {
        "merchant": "Unknown",
        "date": "Unknown",
        "total": 0.0,
        "currency": "USD",
        "tax": 0.0,
    }


def test_parse_receipt_text_merchant_heuristics():
    text = (
        "This is a very long header line that is longer than thirty characters\n"
        "My Coffee Cafe\nLine 3"
    )
    res = receipt_normalizer.parse_receipt_text(text)
    assert res["merchant"] == "My Coffee Cafe"

    text = "Quick Shop\nAddress Line\nDate"
    res = receipt_normalizer.parse_receipt_text(text)
    assert res["merchant"] == "Quick Shop"


def test_parse_receipt_text_dates():
    text = "Date: 2026-07-19\nTotal: 10.00"
    assert receipt_normalizer.parse_receipt_text(text)["date"] == "2026-07-19"

    text = "Date: 19-07-2026\nTotal: 10.00"
    assert receipt_normalizer.parse_receipt_text(text)["date"] == "19-07-2026"

    text = "Date: 19 July 2026\nTotal: 10.00"
    assert receipt_normalizer.parse_receipt_text(text)["date"] == "19 July 2026"

    text = "Date: July 19, 2026\nTotal: 10.00"
    assert receipt_normalizer.parse_receipt_text(text)["date"] == "July 19, 2026"


def test_parse_receipt_text_currency():
    assert receipt_normalizer.parse_receipt_text("Total: €10.00")["currency"] == "EUR"

    assert (
        receipt_normalizer.parse_receipt_text("Total: 10.00 CAD")["currency"] == "CAD"
    )


def test_parse_receipt_text_totals_and_tax():
    text = """
    Target Store Inc
    Date: 2026-07-19
    Item 1: 10.00
    Sales Tax: 1.50
    Total Amount: 11.50
    """
    res = receipt_normalizer.parse_receipt_text(text)
    assert res["total"] == 11.50
    assert res["tax"] == 1.50


def test_parse_receipt_text_european_commas():
    text = """
    Supermarket
    Total: 11,50
    VAT: 1,50
    """
    res = receipt_normalizer.parse_receipt_text(text)
    assert res["total"] == 11.50
    assert res["tax"] == 1.50


def test_parse_receipt_text_fallback_max_amount():
    text = """
    Random Receipt
    10.00
    45.50
    2.00
    """
    res = receipt_normalizer.parse_receipt_text(text)
    assert res["total"] == 45.50


def test_main_no_inputs(capsys):
    with patch("sys.argv", ["receipt_normalizer.py"]), pytest.raises(
        SystemExit
    ) as exc_info:
        receipt_normalizer.main()

    assert exc_info.value.code == 2


def test_main_empty_inputs(capsys):
    with patch("sys.argv", ["receipt_normalizer.py", "nonexistent_dir"]), pytest.raises(
        SystemExit
    ) as exc_info:
        receipt_normalizer.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No valid receipt files found to process." in captured.err


def test_main_process_and_output_json_file(tmp_path):
    text_dir = tmp_path / "receipts"
    text_dir.mkdir()
    receipt1 = text_dir / "r1.txt"
    receipt1.write_text("My Cafe\nTotal: 15.20\nTax: 1.20")

    output_json = tmp_path / "out.json"

    with patch(
        "sys.argv", ["receipt_normalizer.py", str(text_dir), "-o", str(output_json)]
    ):
        receipt_normalizer.main()

    assert os.path.exists(output_json)
    with open(output_json, "r") as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["merchant"] == "My Cafe"
    assert data[0]["total"] == 15.20
    assert data[0]["tax"] == 1.20


def test_main_process_and_output_csv_file(tmp_path):
    text_dir = tmp_path / "receipts"
    text_dir.mkdir()
    receipt1 = text_dir / "r1.txt"
    receipt1.write_text("My Cafe\nTotal: 15.20\nTax: 1.20")

    output_csv = tmp_path / "out.csv"

    with patch(
        "sys.argv", ["receipt_normalizer.py", str(text_dir), "-o", str(output_csv)]
    ):
        receipt_normalizer.main()

    assert os.path.exists(output_csv)
    with open(output_csv, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["merchant"] == "My Cafe"
    assert float(rows[0]["total"]) == 15.20
    assert float(rows[0]["tax"]) == 1.20


def test_main_process_and_stdout_json(capsys, tmp_path):
    receipt1 = tmp_path / "r1.txt"
    receipt1.write_text("My Cafe\nTotal: 15.20\nTax: 1.20")

    with patch("sys.argv", ["receipt_normalizer.py", str(receipt1), "-f", "json"]):
        receipt_normalizer.main()

    captured = capsys.readouterr()
    assert "My Cafe" in captured.out
    json_start = captured.out.find("[")
    data = json.loads(captured.out[json_start:])
    assert len(data) == 1
    assert data[0]["merchant"] == "My Cafe"


def test_main_process_and_stdout_csv(capsys, tmp_path):
    receipt1 = tmp_path / "r1.txt"
    receipt1.write_text("My Cafe\nTotal: 15.20\nTax: 1.20")

    with patch("sys.argv", ["receipt_normalizer.py", str(receipt1), "-f", "csv"]):
        receipt_normalizer.main()

    captured = capsys.readouterr()
    assert "My Cafe" in captured.out
    assert "file_source,merchant,date,currency,total,tax" in captured.out


def test_main_save_error(tmp_path, capsys):
    receipt1 = tmp_path / "r1.txt"
    receipt1.write_text("My Cafe\nTotal: 15.20\nTax: 1.20")

    invalid_output = tmp_path / "invalid_dir"
    invalid_output.mkdir()

    with patch(
        "sys.argv", ["receipt_normalizer.py", str(receipt1), "-o", str(invalid_output)]
    ), pytest.raises(SystemExit) as exc_info:
        receipt_normalizer.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error saving output" in captured.err

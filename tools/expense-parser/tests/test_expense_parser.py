"""Tests for CLI Expense Parser."""

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=import-error, wrong-import-position
import expense_parser  # noqa: E402


def test_parse_amount() -> None:
    """Test bank amount parsing functions."""
    assert expense_parser.parse_amount("$1,234.56") == 1234.56
    assert expense_parser.parse_amount("-$120.00") == -120.00
    assert expense_parser.parse_amount("(150.00)") == -150.00
    assert expense_parser.parse_amount("120,50") == 120.50
    assert expense_parser.parse_amount("1.234,56") == 1234.56
    assert expense_parser.parse_amount("") == 0.0
    assert expense_parser.parse_amount("invalid_val") == 0.0


def test_parse_date() -> None:
    """Test transaction date parsing functions."""
    d1 = expense_parser.parse_date("2026-07-10")
    assert d1 is not None
    assert d1.year == 2026

    d2 = expense_parser.parse_date("10/07/2026")
    assert d2 is not None
    assert d2.day == 10

    d3 = expense_parser.parse_date("10-Jul-26")
    assert d3 is not None
    assert d3.month == 7

    assert expense_parser.parse_date("not a date") is None


def test_categorize_transaction() -> None:
    """Test auto-categorization transaction lookup."""
    rules = {
        "Food": ["starbucks", "grocery"],
        "Rent": ["landlord"],
    }
    assert (
        expense_parser.categorize_transaction("Starbucks Coffee 123", rules) == "Food"
    )
    assert expense_parser.categorize_transaction("Rent to landlord", rules) == "Rent"
    assert expense_parser.categorize_transaction("Unknown payee LLC", rules) == "Other"


def test_detect_columns() -> None:
    """Test column detection header heuristics."""
    header1 = ["trans_date", "payee description", "net value"]
    assert expense_parser.detect_columns(header1) == (0, 2, 1)

    header2 = ["merchant", "charge date", "price sum"]
    assert expense_parser.detect_columns(header2) == (1, 2, 0)


def test_parse_expense_csv(tmp_path: Path) -> None:
    """Test parsing raw CSV rows and mapping columns."""
    p = tmp_path / "bank.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Amount", "Payee"])
        writer.writerow(["2026-07-10", "-15.50", "Starbucks Store"])
        writer.writerow(["2026-07-11", "2000.00", "Direct Deposit payroll"])

    rules = {"Food": ["starbucks"], "Income": ["payroll"]}
    txs, cols = expense_parser.parse_expense_csv(p, rules)

    assert cols == (0, 1, 2)
    assert len(txs) == 2
    assert txs[0]["category"] == "Food"
    assert txs[1]["category"] == "Income"
    assert txs[0]["amount"] == -15.50
    assert txs[1]["amount"] == 2000.00


def test_generate_summaries() -> None:
    """Test aggregating values into monthly savings reports."""
    txs = [
        {
            "date": "2026-07-10",
            "amount": -15.50,
            "category": "Food",
            "description": "Starbucks",
        },
        {
            "date": "2026-07-12",
            "amount": -1000.00,
            "category": "Rent",
            "description": "Housing",
        },
        {
            "date": "2026-07-15",
            "amount": 3000.00,
            "category": "Income",
            "description": "Salary",
        },
    ]
    report = expense_parser.generate_summaries(txs)
    assert "2026-07" in report
    stats = report["2026-07"]
    assert stats["total_income"] == 3000.00
    assert stats["total_expense"] == 1015.50
    assert stats["net_savings"] == 1984.50
    assert stats["savings_rate_pct"] == 66.15
    assert stats["category_expenses"]["Food"] == 15.50


def test_main_cli_formats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main function writing to terminal, JSON, and CSV configurations."""
    csv_in = tmp_path / "bank.csv"
    with open(csv_in, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Amount", "Payee"])
        writer.writerow(["2026-07-10", "-15.50", "Starbucks"])

    out_json = tmp_path / "out.json"
    out_csv = tmp_path / "out.csv"

    # 1. Output to JSON
    args_json = ["expense_parser.py", "-i", str(csv_in), "-o", str(out_json)]
    monkeypatch.setattr(sys, "argv", args_json)
    expense_parser.main()
    assert out_json.exists()

    # 2. Output to CSV
    args_csv = ["expense_parser.py", "-i", str(csv_in), "-o", str(out_csv)]
    monkeypatch.setattr(sys, "argv", args_csv)
    expense_parser.main()
    assert out_csv.exists()


def test_main_cli_custom_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading custom JSON category rules."""
    csv_in = tmp_path / "bank.csv"
    with open(csv_in, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Amount", "Payee"])
        writer.writerow(["2026-07-10", "-50.00", "Custom Store"])

    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps({"Dining": ["store"]}), encoding="utf-8")

    out_json = tmp_path / "out.json"
    args = [
        "expense_parser.py",
        "-i",
        str(csv_in),
        "-r",
        str(rules_file),
        "-o",
        str(out_json),
    ]
    monkeypatch.setattr(sys, "argv", args)
    expense_parser.main()

    saved = json.loads(out_json.read_text(encoding="utf-8"))
    assert saved["transactions"][0]["category"] == "Dining"


def test_main_cli_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI exit codes on bad rule files or missing inputs."""
    # Nonexistent rules
    args = ["expense_parser.py", "-i", "bank.csv", "-r", "nonexistent_rules.json"]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exc:
        expense_parser.main()
    assert exc.value.code == 1

    # Nonexistent input file
    args = ["expense_parser.py", "-i", "nonexistent_bank_file.csv"]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exc:
        expense_parser.main()
    assert exc.value.code == 1

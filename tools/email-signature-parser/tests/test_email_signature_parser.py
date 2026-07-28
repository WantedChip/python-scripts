"""Unit tests for email_signature_parser module."""

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure script directory is on sys.path for direct module import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from email_signature_parser import (  # noqa: E402
    extract_emails,
    extract_name,
    extract_phones,
    extract_title,
    extract_urls,
    main,
    parse_signature,
    setup_cli_parser,
)


def test_extract_emails() -> None:
    """Test extracting email addresses."""
    text = "Contact me at john.doe@example.com or support@company.org!"
    emails = extract_emails(text)
    assert emails == ["john.doe@example.com", "support@company.org"]


def test_extract_phones() -> None:
    """Test extracting phone numbers in various formats."""
    text = "Call +1 (555) 019-2834 or +44 20 7946 0912 ext 104 today."
    phones = extract_phones(text)
    assert len(phones) >= 2
    assert any("555" in p for p in phones)


def test_extract_urls() -> None:
    """Test extracting websites and links."""
    text = "Visit https://www.example.com or www.company.io for info."
    urls = extract_urls(text)
    assert "https://www.example.com" in urls
    assert "www.company.io" in urls


def test_extract_title_and_name() -> None:
    """Test title and name extraction heuristics."""
    lines = [
        "Best regards,",
        "Jane Smith",
        "Senior Software Engineer",
        "Acme Corp",
        "jane.smith@acme.com",
    ]
    title = extract_title(lines)
    assert title == "Senior Software Engineer"

    name = extract_name(lines, title)
    assert name == "Jane Smith"


def test_parse_signature_full() -> None:
    """Test full signature parsing."""
    signature = """
    Thanks,
    Robert Johnson
    Director of Technology
    Email: robert.j@techcorp.com
    Direct: (800) 555-1212
    Web: https://techcorp.com
    """
    res: Dict[str, Any] = parse_signature(signature)
    assert res["name"] == "Robert Johnson"
    assert res["title"] == "Director of Technology"
    assert res["emails"] == ["robert.j@techcorp.com"]
    assert "(800) 555-1212" in res["phones"][0]
    assert res["urls"] == ["https://techcorp.com"]


def test_empty_signature() -> None:
    """Test empty input parsing."""
    res = parse_signature("")
    assert res["name"] is None
    assert res["title"] is None
    assert res["emails"] == []
    assert res["phones"] == []
    assert res["urls"] == []


def test_cli_parser() -> None:
    """Test CLI argument parser flags."""
    parser = setup_cli_parser()
    args = parser.parse_args(["-j", "-v"])
    assert args.json is True
    assert args.verbose is True


def test_main_cli_execution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main CLI entry point with text file input."""
    sig_file = tmp_path / "sig.txt"
    sig_file.write_text(
        "Alice Smith\nLead Developer\nalice@dev.org\nCall (555) 123-4567\n"
    )

    monkeypatch.setattr("sys.argv", ["email_signature_parser.py", str(sig_file)])
    main()

    captured = capsys.readouterr()
    assert "Alice Smith" in captured.out
    assert "Lead Developer" in captured.out
    assert "alice@dev.org" in captured.out


def test_main_cli_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main CLI entry point with JSON output flag."""
    sig_file = tmp_path / "sig.txt"
    sig_file.write_text("Bob Jones\nCTO\nbob@corp.com\n")

    monkeypatch.setattr(
        "sys.argv", ["email_signature_parser.py", str(sig_file), "--json"]
    )
    main()

    captured = capsys.readouterr()
    assert '"name": "Bob Jones"' in captured.out
    assert '"title": "CTO"' in captured.out

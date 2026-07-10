"""Tests for Personal Data Export Searcher."""

# pylint: disable=too-few-public-methods


import csv
import json
import mailbox
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=import-error, wrong-import-position
import data_export_searcher  # noqa: E402


def test_parse_date() -> None:
    """Test date parser with various formats."""
    d1 = data_export_searcher.parse_date("2026-07-10 12:34:56")
    assert d1 is not None
    assert d1.year == 2026
    assert d1.month == 7
    assert d1.day == 10

    d2 = data_export_searcher.parse_date("2026-07-10T12:34:56.789Z")
    assert d2 is not None
    assert d2.microsecond == 789000

    d3 = data_export_searcher.parse_date("2026-07-10")
    assert d3 is not None
    assert d3.hour == 0

    d4 = data_export_searcher.parse_date("Fri, 10 Jul 2026 12:34:56 +0000")
    assert d4 is not None
    assert d4.year == 2026

    assert data_export_searcher.parse_date("InvalidDateString") is None


def test_match_filters() -> None:
    """Test match filter logic for date/sender/query options."""

    class MockArgs:
        """Mock CLI Arguments."""

        query = "hello"
        regex = False
        sender = "Alice"
        subject = "general"
        after = "2026-07-01"
        before = "2026-07-15"

    args = MockArgs()

    # Match all
    assert data_export_searcher.match_filters(
        "Say hello to Alice", "Alice Cooper", "General Room", "2026-07-10", args
    )

    # Content query mismatch
    assert not data_export_searcher.match_filters(
        "Goodbye", "Alice", "general", "2026-07-10", args
    )

    # Sender mismatch
    assert not data_export_searcher.match_filters(
        "hello", "Bob", "general", "2026-07-10", args
    )

    # Subject mismatch
    assert not data_export_searcher.match_filters(
        "hello", "Alice", "random", "2026-07-10", args
    )

    # Date after mismatch
    assert not data_export_searcher.match_filters(
        "hello", "Alice", "general", "2026-06-30", args
    )

    # Date before mismatch
    assert not data_export_searcher.match_filters(
        "hello", "Alice", "general", "2026-07-20", args
    )


def test_match_filters_regex() -> None:
    """Test regular expression matching filter."""

    class MockArgs:
        """Mock args."""

        query = r"^hello\s\d+"
        regex = True
        sender = None
        subject = None
        after = None
        before = None

    args = MockArgs()

    assert data_export_searcher.match_filters("hello 123 world", None, None, None, args)
    assert not data_export_searcher.match_filters(
        "say hello 123", None, None, None, args
    )


def test_search_json(tmp_path: Path) -> None:
    """Test parsing and searching structured JSON archives."""
    p = tmp_path / "chat.json"
    data = [
        {"author": "Alice", "timestamp": "2026-07-10", "content": "Hello everyone"},
        {"author": "Bob", "timestamp": "2026-07-11", "content": "Hi Alice"},
    ]
    p.write_text(json.dumps(data), encoding="utf-8")

    class MockArgs:
        """Mock args."""

        query = "hello"
        regex = False
        sender = None
        subject = None
        after = None
        before = None

    results = list(data_export_searcher.search_json(p, MockArgs()))
    assert len(results) == 1
    assert results[0].sender == "Alice"
    assert results[0].content == "Hello everyone"


def test_search_csv(tmp_path: Path) -> None:
    """Test parsing and searching CSV log files."""
    p = tmp_path / "logs.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Time", "Author", "Subject", "Message"])
        writer.writerow(["2026-07-10", "Alice", "general", "Hello from Alice"])
        writer.writerow(["2026-07-11", "Bob", "general", "Goodbye"])

    class MockArgs:
        """Mock args."""

        query = "hello"
        regex = False
        sender = None
        subject = None
        after = None
        before = None

    results = list(data_export_searcher.search_csv(p, MockArgs()))
    assert len(results) == 1
    assert results[0].sender == "Alice"
    assert results[0].subject == "general"


def test_search_mbox(tmp_path: Path) -> None:
    """Test searching through MBOX files using mailbox module."""
    p = tmp_path / "email.mbox"

    # Create MBOX file and write a sample mail message
    mbox = mailbox.mbox(p)
    msg = mailbox.mboxMessage()
    msg["From"] = "Alice <alice@example.com>"
    msg["Date"] = "Fri, 10 Jul 2026 12:34:56 +0000"
    msg["Subject"] = "Welcome Topic"
    msg.set_payload("Hello MBOX reader body!")
    mbox.add(msg)
    mbox.close()

    class MockArgs:
        """Mock args."""

        query = "mbox"
        regex = False
        sender = None
        subject = None
        after = None
        before = None

    results = list(data_export_searcher.search_mbox(p, MockArgs()))
    assert len(results) == 1
    assert results[0].sender == "Alice <alice@example.com>"
    assert "mbox" in results[0].content.lower()


def test_search_html(tmp_path: Path) -> None:
    """Test searching HTML page text markup."""
    p = tmp_path / "chat.html"
    p.write_text(
        "<html><head><title>Room Name</title></head>"
        "<body><p>Hello message line 1</p><p>Goodbye line 2</p></body></html>",
        encoding="utf-8",
    )

    class MockArgs:
        """Mock args."""

        query = "hello"
        regex = False
        sender = None
        subject = None
        after = None
        before = None

    results = list(data_export_searcher.search_html(p, MockArgs()))
    assert len(results) == 1
    assert results[0].subject == "Room Name"
    assert results[0].content == "Hello message line 1"


def test_execute_search_recursive(tmp_path: Path) -> None:
    """Test directory walking search execution."""
    d = tmp_path / "archive"
    d.mkdir()
    json_path = d / "data.json"
    json_path.write_text(
        json.dumps([{"content": "hello searcher", "sender": "Alice"}]), encoding="utf-8"
    )

    class MockArgs:
        """Mock args."""

        input = str(d)
        query = "searcher"
        regex = False
        sender = None
        subject = None
        after = None
        before = None

    results = data_export_searcher.execute_search(MockArgs())
    assert len(results) == 1
    assert results[0].sender == "Alice"


def test_main_cli_prints_and_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main function writing to JSON and CSV files."""
    d = tmp_path / "chat.json"
    d.write_text(
        json.dumps([{"content": "hello searcher", "sender": "Alice"}]), encoding="utf-8"
    )
    out_json = tmp_path / "results.json"
    out_csv = tmp_path / "results.csv"

    # Test saving as JSON
    args_json = [
        "data_export_searcher.py",
        "-i",
        str(d),
        "-q",
        "searcher",
        "-o",
        str(out_json),
        "--format",
        "json",
    ]
    monkeypatch.setattr(sys, "argv", args_json)
    data_export_searcher.main()

    assert out_json.exists()
    saved_data = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(saved_data) == 1
    assert saved_data[0]["sender"] == "Alice"

    # Test saving as CSV
    args_csv = [
        "data_export_searcher.py",
        "-i",
        str(d),
        "-q",
        "searcher",
        "-o",
        str(out_csv),
        "--format",
        "csv",
    ]
    monkeypatch.setattr(sys, "argv", args_csv)
    data_export_searcher.main()

    assert out_csv.exists()

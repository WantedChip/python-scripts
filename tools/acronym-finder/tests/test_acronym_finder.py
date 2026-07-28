"""Unit tests for acronym_finder module."""

import sys
from pathlib import Path
from typing import List

import pytest

# Ensure script directory is on sys.path for direct module import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from acronym_finder import (  # noqa: E402
    AcronymMatch,
    clean_acronym,
    export_csv,
    format_text_output,
    main,
    scan_acronyms,
    setup_cli_parser,
)


def test_clean_acronym() -> None:
    """Test acronym normalization."""
    assert clean_acronym("U.S.A.") == "USA"
    assert clean_acronym("API") == "API"


def test_scan_acronyms_basic() -> None:
    """Test scanning basic acronyms in text."""
    doc = """
    Line 1: We are introducing a new Application Programming Interface (API) today.
    Line 2: The API communicates over HTTP and HTTPS protocols.
    Line 3: Located in the U.S.A.
    """
    results: List[AcronymMatch] = scan_acronyms(doc)

    acronyms = [r.acronym for r in results]
    assert "API" in acronyms
    assert "HTTP" in acronyms
    assert "HTTPS" in acronyms
    assert "USA" in acronyms

    # Test first occurrence line number
    api_match = next(r for r in results if r.acronym == "API")
    assert api_match.line_number == 2
    assert api_match.expansion == "Application Programming Interface"


def test_scan_acronyms_min_length() -> None:
    """Test filtering by minimum length."""
    doc = "AI is great. IT departments use IP addresses."
    results = scan_acronyms(doc, min_length=3)
    acronyms = [r.acronym for r in results]
    assert "AI" not in acronyms
    assert "IT" not in acronyms
    assert "IP" not in acronyms


def test_format_text_output() -> None:
    """Test formatting output text."""
    matches = [
        AcronymMatch(
            acronym="JSON",
            line_number=5,
            context="Data format is JSON.",
            expansion=None,
        )
    ]
    out = format_text_output(matches)
    assert "JSON" in out
    assert "5" in out

    empty_out = format_text_output([])
    assert "No acronyms found." in empty_out


def test_export_csv() -> None:
    """Test CSV export format."""
    matches = [
        AcronymMatch(
            acronym="CPU",
            line_number=1,
            context="Central Processing Unit (CPU) utilization is low.",
            expansion="Central Processing Unit",
        )
    ]
    csv_out = export_csv(matches)
    assert "acronym,line_number,expansion,context" in csv_out
    assert "CPU,1,Central Processing Unit" in csv_out


def test_cli_parser() -> None:
    """Test CLI parser flags."""
    parser = setup_cli_parser()
    args = parser.parse_args(["-f", "json", "-m", "4", "-v"])
    assert args.format == "json"
    assert args.min_length == 4
    assert args.verbose is True


def test_main_cli_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main CLI entry point with text file input."""
    sample_file = tmp_path / "doc.txt"
    sample_file.write_text("World Health Organization (WHO) report.\nWHO details.\n")

    monkeypatch.setattr("sys.argv", ["acronym_finder.py", str(sample_file)])
    main()

    captured = capsys.readouterr()
    assert "WHO" in captured.out
    assert "World Health Organization" in captured.out


def test_main_cli_json_and_csv(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main CLI entry point with JSON and CSV export formats."""
    sample_file = tmp_path / "doc.txt"
    sample_file.write_text("File Transfer Protocol (FTP) server.\n")

    monkeypatch.setattr(
        "sys.argv", ["acronym_finder.py", str(sample_file), "--format", "json"]
    )
    main()
    captured_json = capsys.readouterr()
    assert '"acronym": "FTP"' in captured_json.out

    monkeypatch.setattr(
        "sys.argv", ["acronym_finder.py", str(sample_file), "--format", "csv"]
    )
    main()
    captured_csv = capsys.readouterr()
    assert "FTP,1,File Transfer Protocol" in captured_csv.out

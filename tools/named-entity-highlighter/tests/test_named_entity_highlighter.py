"""Unit tests for named_entity_highlighter module."""

import sys
from pathlib import Path
from typing import List

import pytest

# Ensure script directory is on sys.path for direct module import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from named_entity_highlighter import (  # noqa: E402
    EntityMatch,
    extract_entities,
    highlight_ansi,
    highlight_html,
    highlight_markdown,
    main,
    setup_cli_parser,
)


def test_extract_entities() -> None:
    """Test extracting names, dates, organizations, and locations."""
    sample = "Dr. Alice Smith visited Acme Corp in New York City on 2026-07-28."
    entities: List[EntityMatch] = extract_entities(sample)

    labels = [e.label for e in entities]
    assert "NAME" in labels
    assert "ORG" in labels
    assert "LOCATION" in labels
    assert "DATE" in labels

    name_ent = next(e for e in entities if e.label == "NAME")
    assert "Alice Smith" in name_ent.text


def test_highlight_ansi() -> None:
    """Test ANSI color output formatting."""
    entities = [EntityMatch(text="Acme Corp", label="ORG", start=0, end=9)]
    text = "Acme Corp is open."
    ansi_out = highlight_ansi(text, entities)
    assert "\033[93mAcme Corp\033[0m" in ansi_out


def test_highlight_html() -> None:
    """Test HTML mark output formatting."""
    entities = [EntityMatch(text="2026-07-28", label="DATE", start=12, end=22)]
    text = "Scheduled on 2026-07-28."
    html_out = highlight_html(text, entities)
    assert '<mark class="entity-date" data-entity="DATE">2026-07-28</mark>' in html_out


def test_highlight_markdown() -> None:
    """Test Markdown bold tag output formatting."""
    entities = [EntityMatch(text="New York City", label="LOCATION", start=3, end=16)]
    text = "In New York City today."
    md_out = highlight_markdown(text, entities)
    assert "**New York City**`[LOCATION]`" in md_out


def test_cli_parser() -> None:
    """Test CLI parser argument flags."""
    parser = setup_cli_parser()
    args = parser.parse_args(["-f", "html", "-v"])
    assert args.format == "html"
    assert args.verbose is True


def test_main_cli_formats(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main CLI execution across multiple export formats."""
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("Dr. Jane Doe visited Google Inc on January 15, 2026.")

    monkeypatch.setattr(
        "sys.argv",
        ["named_entity_highlighter.py", str(sample_file), "-f", "json"],
    )
    main()
    captured_json = capsys.readouterr()
    assert '"entity": "Google Inc"' in captured_json.out
    assert '"label": "ORG"' in captured_json.out

    monkeypatch.setattr(
        "sys.argv",
        ["named_entity_highlighter.py", str(sample_file), "-f", "markdown"],
    )
    main()
    captured_md = capsys.readouterr()
    assert "**Google Inc**`[ORG]`" in captured_md.out

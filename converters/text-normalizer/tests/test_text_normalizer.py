"""Unit tests for text_normalizer module."""

import sys
from pathlib import Path

import pytest

# Ensure script directory is on sys.path for direct module import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from text_normalizer import (  # noqa: E402
    expand_contractions,
    main,
    normalize_smart_quotes,
    normalize_text,
    remove_accents,
    setup_cli_parser,
    standardize_whitespace,
)


def test_expand_contractions() -> None:
    """Test contraction expansion for lowercase, capitalized, and uppercase."""
    text = "Don't go! It's late and I won't leave. WE'RE READY."
    expanded = expand_contractions(text)
    assert "Do not go!" in expanded
    assert "It is late" in expanded
    assert "will not leave" in expanded
    assert "WE ARE READY" in expanded


def test_remove_accents() -> None:
    """Test removing accents and diacritics."""
    text = "café, résumé, naïve, façade, Señor"
    cleaned = remove_accents(text)
    assert cleaned == "cafe, resume, naive, facade, Senor"


def test_normalize_smart_quotes() -> None:
    """Test converting smart quotes to ASCII."""
    text = "“Hello world,” said ‘Alice’."
    cleaned = normalize_smart_quotes(text)
    assert cleaned == "\"Hello world,\" said 'Alice'."


def test_standardize_whitespace() -> None:
    """Test space and newline normalization."""
    text = "  Hello   world!  \n\n\n  This   is   a test.  "
    cleaned = standardize_whitespace(text, remove_extra_newlines=True)
    assert "Hello world!" in cleaned
    assert "This is a test." in cleaned


def test_normalize_text_pipeline() -> None:
    """Test full normalization pipeline."""
    raw = "  They're   enjoying   café   latté!  "
    result = normalize_text(raw, lowercase=True)
    assert result == "they are enjoying cafe latte!"


def test_cli_parser() -> None:
    """Test CLI parser flags."""
    parser = setup_cli_parser()
    args = parser.parse_args(["--no-contractions", "--keep-accents", "-l"])
    assert args.no_contractions is True
    assert args.keep_accents is True
    assert args.lowercase is True


def test_main_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main CLI execution with input and output files."""
    in_file = tmp_path / "input.txt"
    out_file = tmp_path / "output.txt"
    in_file.write_text("It's a café.\n", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        ["text_normalizer.py", str(in_file), "-o", str(out_file)],
    )
    main()

    res = out_file.read_text(encoding="utf-8")
    assert "It is a cafe." in res

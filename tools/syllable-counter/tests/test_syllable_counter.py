"""Unit tests for syllable_counter module."""

import sys
from pathlib import Path

import pytest

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from syllable_counter import analyze_text, count_syllables_word, main  # noqa: E402


def test_count_syllables_word_basic() -> None:
    """Test basic word syllable counts."""
    assert count_syllables_word("cat") == 1
    assert count_syllables_word("apple") == 2
    assert count_syllables_word("banana") == 3
    assert count_syllables_word("understanding") == 4
    assert count_syllables_word("") == 0


def test_count_syllables_word_exceptions() -> None:
    """Test exception dictionary words."""
    assert count_syllables_word("really") == 2
    assert count_syllables_word("area") == 3
    assert count_syllables_word("chocolate") == 3


def test_analyze_text() -> None:
    """Test full passage text analysis and readability metrics."""
    passage = "The quick brown fox jumps over the lazy dog. Simple sentences work well."
    words, summary = analyze_text(passage)
    assert len(words) > 0
    assert summary["total_words"] == 13
    assert summary["total_syllables"] >= 13
    assert summary["avg_syllables_per_word"] > 0
    assert "flesch_reading_ease" in summary


def test_cli_word_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI --word option."""
    ret = main(["--word", "extraordinary"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "extraordinary" in captured.out


def test_cli_json_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI JSON output format."""
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Python scripts work cleanly.")
    ret = main([str(file_path), "-f", "json"])
    assert ret == 0
    captured = capsys.readouterr()
    assert '"total_words": 4' in captured.out
    assert '"summary"' in captured.out


def test_cli_empty_word(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI word option with empty string."""
    ret = main(["--word", ""])
    assert ret == 0
    captured = capsys.readouterr()
    assert "0 syllable(s)" in captured.out


def test_cli_no_input() -> None:
    """Test CLI returning error code 1 when no input is supplied."""
    ret = main([])
    assert ret == 1

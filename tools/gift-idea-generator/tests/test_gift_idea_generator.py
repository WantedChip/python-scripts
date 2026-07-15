"""Tests for gift_idea_generator.py."""

import json
import os
import sys

import pytest

# Add current folder to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error
from gift_idea_generator import (  # noqa: E402
    format_gift_ideas_markdown,
    generate_gift_ideas,
    load_gifts_database,
    main,
    score_gift,
)


def test_load_gifts_database(tmp_path: pytest.TempPathFactory) -> None:
    """Tests load_gifts_database function."""
    # Built-in check
    gifts = load_gifts_database(None)
    assert len(gifts) > 0

    # Custom valid JSON load
    custom_data = [
        {
            "name": "Custom Mug",
            "price": 10.0,
            "ages": ["adult"],
            "interests": ["general"],
            "relationships": ["friend"],
            "desc": "A custom mug.",
        }
    ]
    custom_file = tmp_path / "custom_gifts.json"
    custom_file.write_text(json.dumps(custom_data), encoding="utf-8")

    loaded = load_gifts_database(str(custom_file))
    assert len(loaded) == 1
    assert loaded[0]["name"] == "Custom Mug"
    assert isinstance(loaded[0]["ages"], set)

    # Missing file path check (should fallback to built-ins)
    assert len(load_gifts_database("does_not_exist.json")) > 0


def test_score_gift() -> None:
    """Tests score_gift function."""
    gift = {
        "name": "Test Gift",
        "price": 50.0,
        "ages": {"adult"},
        "interests": {"gaming", "tech"},
        "relationships": {"friend"},
    }

    # Matches interest, age, relationship
    assert score_gift(gift, "adult", "friend", {"gaming"}) == 6  # 3 + 2 + 1
    # Matches multiple interests
    assert score_gift(gift, "adult", "friend", {"gaming", "tech"}) == 9  # 6 + 2 + 1
    # No matches at all
    assert score_gift(gift, "child", "colleague", {"cooking"}) == 0


def test_generate_gift_ideas() -> None:
    """Tests generate_gift_ideas function."""
    # Hypertrophy budget test
    ideas = generate_gift_ideas("adult", 30.0, "tech,fitness", "friend", 3)
    # Wireless charging pad is 20.0, water bottle is 25.0, resistance bands are 15.0
    assert len(ideas) > 0
    for gift in ideas:
        assert gift["price"] <= 30.0

    # Fallback verification
    fallback_ideas = generate_gift_ideas("child", 5.0, "cooking", "colleague", 2)
    assert len(fallback_ideas) == 1
    assert fallback_ideas[0]["name"] == "Custom Gift Card (Bookstore/Coffee)"
    assert fallback_ideas[0]["price"] == 5.0


def test_format_gift_ideas_markdown() -> None:
    """Tests format_gift_ideas_markdown function."""
    ideas = generate_gift_ideas("teen", 50.0, "art", "sibling", 2)
    markdown_str = format_gift_ideas_markdown(ideas, "teen", 50.0, "art", "sibling")
    assert "# Gift Recommendations Guide" in markdown_str
    assert "Teen" in markdown_str
    assert "Sibling" in markdown_str
    assert "1. " in markdown_str


def test_main_cli(
    tmp_path: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests main CLI interface."""
    # Stdout markdown verification
    monkeypatch.setattr(
        sys,
        "argv",
        ["gift_idea_generator.py", "-a", "adult", "-b", "100", "-i", "tech"],
    )
    main()
    captured = capsys.readouterr()
    assert "# Gift Recommendations Guide" in captured.out
    assert "Mechanical Keyboard" in captured.out

    # Invalid budget constraint check
    monkeypatch.setattr(sys, "argv", ["gift_idea_generator.py", "-b", "0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Budget must be greater than zero" in captured.err

    # Invalid num_gifts constraint check
    monkeypatch.setattr(sys, "argv", ["gift_idea_generator.py", "-n", "0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Number of gifts must be at least 1" in captured.err

    # Save to file verification
    output_file = tmp_path / "gifts.md"
    monkeypatch.setattr(sys, "argv", ["gift_idea_generator.py", "-o", str(output_file)])
    main()
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "# Gift Recommendations Guide" in content
    capsys.readouterr()  # Clear buffer

    # Output JSON verification
    monkeypatch.setattr(sys, "argv", ["gift_idea_generator.py", "--format", "json"])
    main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) > 0

"""Tests for random_name_generator.py."""

import json
import os
import sys

import pytest

# Add current folder to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error
from random_name_generator import (  # noqa: E402
    format_names_markdown,
    generate_names,
    generate_syllabic_name,
    load_pools_database,
    main,
)


def test_load_pools_database(tmp_path: pytest.TempPathFactory) -> None:
    """Tests load_pools_database function."""
    # Built-in check
    pools = load_pools_database(None)
    assert "people" in pools
    assert "projects" in pools

    # Custom valid JSON load
    custom_data = {"people": {"classic": ["Alice", "Bob"]}}
    custom_file = tmp_path / "custom_pools.json"
    custom_file.write_text(json.dumps(custom_data), encoding="utf-8")

    loaded = load_pools_database(str(custom_file))
    assert "people" in loaded
    assert loaded["people"]["classic"] == ["Alice", "Bob"]

    # Missing file path check (should fallback to built-ins)
    assert len(load_pools_database("does_not_exist.json")) > 0


def test_generate_syllabic_name() -> None:
    """Tests generate_syllabic_name function."""
    prefixes = ["Alpha", "Beta"]
    suffixes = ["core", "flow"]

    # Regular generation
    name = generate_syllabic_name(prefixes, suffixes)
    assert any(name.startswith(p) for p in prefixes)
    assert any(name.endswith(s) for s in suffixes)

    # Alliterate generation (matching starting char 'a'/'A')
    name_allit = generate_syllabic_name(prefixes, suffixes, "a")
    assert name_allit.startswith("Alpha")


def test_generate_names() -> None:
    """Tests generate_names function."""
    # Tech projects syllable-based generation
    names = generate_names("projects", "tech", 3)
    assert len(names) == 3
    for name in names:
        assert isinstance(name, str)
        assert len(name) > 0

    # Modern people list-based generation
    people_names = generate_names("people", "modern", 2)
    assert len(people_names) == 2

    # Alliterate list-based generation (creates double names)
    allit_people = generate_names("people", "modern", 2, alliterate=True)
    assert len(allit_people) == 2
    for n in allit_people:
        parts = n.split(" ")
        assert len(parts) == 2
        # Check alliterative starts
        assert parts[0][0].lower() == parts[1][0].lower()

    # Fallback to general category pool list on invalid style
    fallback_names = generate_names("pets", "invalid-style", 2)
    assert len(fallback_names) == 2

    # Fallback to category name patterns on invalid category
    invalid_cat_names = generate_names("invalid-cat", "tech", 2)
    assert len(invalid_cat_names) == 2
    assert invalid_cat_names[0].startswith("Unknown-Category-Name-")


def test_format_names_markdown() -> None:
    """Tests format_names_markdown function."""
    names = ["Eldrin", "Lyra"]
    markdown_str = format_names_markdown(names, "people", "fantasy", False)
    assert "# Generated Suggestions" in markdown_str
    assert "**Category**: People" in markdown_str
    assert "Eldrin" in markdown_str


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
        ["random_name_generator.py", "-c", "projects", "-s", "tech", "-q", "3"],
    )
    main()
    captured = capsys.readouterr()
    assert "# Generated Suggestions" in captured.out

    # Invalid quantity constraint check (low)
    monkeypatch.setattr(sys, "argv", ["random_name_generator.py", "-q", "0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Quantity must be between 1 and 50" in captured.err

    # Invalid quantity constraint check (high)
    monkeypatch.setattr(sys, "argv", ["random_name_generator.py", "-q", "100"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Quantity must be between 1 and 50" in captured.err

    # Save to file verification
    output_file = tmp_path / "names.md"
    monkeypatch.setattr(
        sys, "argv", ["random_name_generator.py", "-o", str(output_file)]
    )
    main()
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "# Generated Suggestions" in content
    capsys.readouterr()  # Clear buffer

    # Output JSON verification
    monkeypatch.setattr(sys, "argv", ["random_name_generator.py", "--format", "json"])
    main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) > 0

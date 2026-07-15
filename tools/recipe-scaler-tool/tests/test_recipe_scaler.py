"""Tests for recipe_scaler.py."""

import json
import os
import sys
from fractions import Fraction

import pytest

# Add current folder to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error
from recipe_scaler import (  # noqa: E402
    convert_unit,
    format_quantity,
    main,
    parse_fraction,
    parse_ingredient_line,
    scale_recipe_json,
    scale_recipe_text,
)


def test_parse_fraction() -> None:
    """Tests parse_fraction function."""
    assert parse_fraction("2") == Fraction(2)
    assert parse_fraction("1.5") == Fraction(3, 2)
    assert parse_fraction("1/2") == Fraction(1, 2)
    assert parse_fraction("1 1/2") == Fraction(3, 2)
    assert parse_fraction("1-1/2") == Fraction(3, 2)
    assert parse_fraction("") == Fraction(0)

    with pytest.raises(ValueError):
        parse_fraction("abc")


def test_format_quantity() -> None:
    """Tests format_quantity function."""
    assert format_quantity(Fraction(2), False) == "2"
    assert format_quantity(Fraction(3, 2), False) == "1 1/2"
    assert format_quantity(Fraction(1, 3), False) == "1/3"
    assert format_quantity(Fraction(5, 8), False) == "5/8"
    assert format_quantity(Fraction(3, 2), True) == "1.5"
    assert format_quantity(Fraction(1, 3), True) == "0.33"
    assert format_quantity(Fraction(0), False) == ""

    # Test rounding for non-standard denominator.
    # 7/9 is 0.7777... closest standard is 3/4 (0.75) or 4/5?
    # Standard are halves, thirds, fourths, eighths.
    # So it should be 3/4
    assert format_quantity(Fraction(7, 9), False) == "3/4"
    assert format_quantity(Fraction(1, 100), False) == ""  # rounds to 0


def test_convert_unit() -> None:
    """Tests convert_unit function."""
    # Imperial to Metric
    assert convert_unit(Fraction(1), "cups", "metric") == (Fraction(240), "ml")
    assert convert_unit(Fraction(5), "cups", "metric") == (
        Fraction(6, 5),
        "l",
    )  # 1200 ml = 1.2 l
    assert convert_unit(Fraction(1), "lbs", "metric") == (Fraction("453.59"), "g")
    assert convert_unit(Fraction(3), "lbs", "metric") == (Fraction(777, 571), "kg")

    # Metric to Imperial
    assert convert_unit(Fraction(240), "ml", "imperial") == (Fraction(1), "cups")
    assert convert_unit(Fraction(120), "ml", "imperial") == (
        Fraction(4),
        "fl oz",
    )  # wait, 120/30 = 4 fl oz
    assert convert_unit(Fraction(15), "ml", "imperial") == (Fraction(1), "tbsp")
    assert convert_unit(Fraction(5), "ml", "imperial") == (Fraction(1), "tsp")
    assert convert_unit(Fraction("453.59"), "g", "imperial") == (Fraction(1), "lbs")

    # No conversion
    assert convert_unit(Fraction(2), "cups", "none") == (Fraction(2), "cups")


def test_parse_ingredient_line() -> None:
    """Tests parse_ingredient_line function."""
    assert parse_ingredient_line("1 1/2 cups flour") == ("1 1/2", "cups", "flour")
    assert parse_ingredient_line("2 tbsp sugar") == ("2", "tbsp", "sugar")
    assert parse_ingredient_line("salt to taste") == (None, None, "salt to taste")
    assert parse_ingredient_line("4 eggs") == ("4", None, "eggs")
    assert parse_ingredient_line("1-2 cups milk") == ("1-2", "cups", "milk")
    assert parse_ingredient_line("") == (None, None, "")


def test_scale_recipe_text() -> None:
    """Tests scale_recipe_text function."""
    recipe = (
        "Ingredients:\n"
        "1 cup sugar\n"
        "1/2 tsp salt\n"
        "1-2 cups flour\n"
        "Instructions:\n"
        "Mix 1 cup sugar with flour."
    )
    scaled = scale_recipe_text(recipe, Fraction(2), "none", False)
    expected = (
        "Ingredients:\n"
        "2 cups sugar\n"
        "1 tsp salt\n"
        "2-4 cups flour\n"
        "Instructions:\n"
        "Mix 1 cup sugar with flour."
    )
    assert scaled.strip() == expected.strip()


def test_scale_recipe_json() -> None:
    """Tests scale_recipe_json function."""
    recipe = {
        "servings": 4,
        "ingredients": [
            {"quantity": "1 1/2", "unit": "cups", "name": "flour"},
            {"quantity": "2", "name": "eggs"},
            {"name": "salt"},
        ],
    }
    recipe_str = json.dumps(recipe)
    scaled_str = scale_recipe_json(recipe_str, Fraction(2), "none", False)
    scaled = json.loads(scaled_str)

    assert scaled["servings"] == 8.0
    assert scaled["original_servings"] == 4
    assert scaled["ingredients"][0]["quantity"] == "3"
    assert scaled["ingredients"][1]["quantity"] == "4"

    # Test invalid JSON error
    with pytest.raises(ValueError):
        scale_recipe_json("invalid-json", Fraction(2), "none", False)


def test_main_cli(
    tmp_path: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests main CLI interface."""
    recipe_content = "servings: 4\n" "Ingredients:\n" "2 cups milk\n"
    recipe_file = tmp_path / "recipe.txt"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    # Call with factor
    monkeypatch.setattr(
        sys, "argv", ["recipe_scaler.py", str(recipe_file), "-f", "2.0"]
    )
    main()
    captured = capsys.readouterr()
    assert "4 cups milk" in captured.out

    # Call with servings
    monkeypatch.setattr(sys, "argv", ["recipe_scaler.py", str(recipe_file), "-s", "8"])
    main()
    captured = capsys.readouterr()
    assert "4 cups milk" in captured.out

    # Call with servings and manual original servings
    monkeypatch.setattr(
        sys, "argv", ["recipe_scaler.py", str(recipe_file), "-s", "8", "-o", "4"]
    )
    main()
    captured = capsys.readouterr()
    assert "4 cups milk" in captured.out

    # Call with non-existent file
    monkeypatch.setattr(
        sys, "argv", ["recipe_scaler.py", "doesnotexist.txt", "-f", "2.0"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err

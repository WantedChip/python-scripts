"""Unit tests for Cocktail Recipe Fetcher."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import (
    export_json,
    extract_ingredients,
    filter_cocktails_by_ingredient,
    format_recipe_card,
    get_random_cocktail,
    search_cocktail_by_name,
)


class TestCocktailFetcher(unittest.TestCase):
    """Test suite for cocktail recipe fetcher functions."""

    def setUp(self) -> None:
        self.sample_drink = {
            "idDrink": "11007",
            "strDrink": "Margarita",
            "strCategory": "Ordinary Drink",
            "strAlcoholic": "Alcoholic",
            "strGlass": "Cocktail glass",
            "strInstructions": (
                "Rub the rim of the glass with lime juice. "
                "Shake all ingredients with ice."
            ),
            "strDrinkThumb": (
                "https://www.thecocktaildb.com/images/media/"
                "drink/5noda61589575158.jpg"
            ),
            "strIngredient1": "Tequila",
            "strMeasure1": "1 1/2 oz",
            "strIngredient2": "Triple sec",
            "strMeasure2": "1/2 oz",
            "strIngredient3": "Lime juice",
            "strMeasure3": "1 oz",
            "strIngredient4": None,
            "strMeasure4": None,
        }

    def test_extract_ingredients(self) -> None:
        """Test extracting combined ingredient and measurement strings."""
        ingredients = extract_ingredients(self.sample_drink)
        self.assertEqual(len(ingredients), 3)
        self.assertEqual(ingredients[0], "1 1/2 oz Tequila")
        self.assertEqual(ingredients[1], "1/2 oz Triple sec")
        self.assertEqual(ingredients[2], "1 oz Lime juice")

    def test_format_recipe_card(self) -> None:
        """Test recipe card formatting."""
        card = format_recipe_card(self.sample_drink)
        self.assertIn("MARGARITA", card)
        self.assertIn("Cocktail glass", card)
        self.assertIn("1 1/2 oz Tequila", card)
        self.assertIn("Rub the rim of the glass", card)

    @patch("main.fetch_json")
    def test_search_cocktail_by_name(self, mock_fetch: MagicMock) -> None:
        """Test searching cocktail by name API call."""
        mock_fetch.return_value = {"drinks": [self.sample_drink]}
        results = search_cocktail_by_name("margarita")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["strDrink"], "Margarita")

    @patch("main.fetch_json")
    def test_filter_cocktails_by_ingredient(self, mock_fetch: MagicMock) -> None:
        """Test filtering cocktails by ingredient."""
        mock_fetch.return_value = {
            "drinks": [{"strDrink": "Margarita", "idDrink": "11007"}]
        }
        results = filter_cocktails_by_ingredient("tequila")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["strDrink"], "Margarita")

    @patch("main.fetch_json")
    def test_get_random_cocktail(self, mock_fetch: MagicMock) -> None:
        """Test random cocktail retrieval."""
        mock_fetch.return_value = {"drinks": [self.sample_drink]}
        drink = get_random_cocktail()
        self.assertIsNotNone(drink)
        self.assertEqual(drink["strDrink"], "Margarita")

    def test_export_json(self) -> None:
        """Test exporting recipes to JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "recipes.json")
            success = export_json([self.sample_drink], file_path)
            self.assertTrue(success)
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            self.assertEqual(len(content), 1)
            self.assertEqual(content[0]["name"], "Margarita")


if __name__ == "__main__":
    unittest.main()

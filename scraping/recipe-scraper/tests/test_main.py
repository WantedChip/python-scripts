"""Unit tests for Recipe Scraper."""

import unittest

from main import (
    extract_recipe,
    find_recipe_json_ld,
    parse_iso_duration,
    parse_recipe_from_json_ld,
    recipe_to_markdown,
)


class TestRecipeScraper(unittest.TestCase):
    """Test suite for ISO duration parsing, JSON-LD extraction, and formatting."""

    def test_parse_iso_duration(self) -> None:
        self.assertEqual(parse_iso_duration("PT15M"), "15 mins")
        self.assertEqual(parse_iso_duration("PT1H30M"), "1 hr 30 mins")
        self.assertEqual(parse_iso_duration("P1DT2H"), "1 day 2 hrs")
        self.assertEqual(parse_iso_duration("15 mins"), "15 mins")

    def test_find_recipe_json_ld(self) -> None:
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": "Chocolate Chip Cookies",
            "recipeIngredient": ["1 cup flour", "1/2 cup sugar"],
            "recipeInstructions": ["Mix ingredients.", "Bake at 350F."]
        }
        </script>
        </head>
        <body></body>
        </html>
        """
        json_ld = find_recipe_json_ld(html)
        self.assertIsNotNone(json_ld)
        self.assertEqual(json_ld.get("name"), "Chocolate Chip Cookies")

    def test_parse_recipe_from_json_ld(self) -> None:
        json_ld = {
            "@type": "Recipe",
            "name": "Classic Pancakes",
            "description": "Fluffy breakfast pancakes",
            "author": {"name": "Chef John"},
            "prepTime": "PT10M",
            "cookTime": "PT15M",
            "recipeYield": "4 servings",
            "recipeIngredient": ["1 cup flour", "1 egg", "1 cup milk"],
            "recipeInstructions": [
                {"@type": "HowToStep", "text": "Whisk ingredients together."},
                {"@type": "HowToStep", "text": "Cook on griddle until golden."},
            ],
        }
        recipe = parse_recipe_from_json_ld(json_ld)
        self.assertEqual(recipe.title, "Classic Pancakes")
        self.assertEqual(recipe.author, "Chef John")
        self.assertEqual(recipe.prep_time, "10 mins")
        self.assertEqual(recipe.cook_time, "15 mins")
        self.assertEqual(len(recipe.ingredients), 3)
        self.assertEqual(len(recipe.instructions), 2)
        self.assertIn("Whisk ingredients together.", recipe.instructions)

    def test_extract_recipe_and_markdown(self) -> None:
        html = """
        <html>
        <script type="application/ld+json">
        {
            "@type": "Recipe",
            "name": "Guacamole",
            "recipeIngredient": ["3 avocados", "1 lime"],
            "recipeInstructions": ["Mash avocados with lime juice."]
        }
        </script>
        </html>
        """
        recipe = extract_recipe(html)
        self.assertEqual(recipe.title, "Guacamole")
        md = recipe_to_markdown(recipe)
        self.assertIn("# Guacamole", md)
        self.assertIn("- 3 avocados", md)
        self.assertIn("1. Mash avocados with lime juice.", md)


if __name__ == "__main__":
    unittest.main()

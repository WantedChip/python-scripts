"""Unit tests for Cocktail Recipe Fetcher."""

import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    export_json,
    extract_ingredients,
    fetch_json,
    filter_cocktails_by_ingredient,
    format_recipe_card,
    get_cocktail_details,
    get_random_cocktail,
    main,
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

    def test_export_json_oserror(self) -> None:
        """Unwritable export targets report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing" / "recipes.json")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = export_json([self.sample_drink], bad_path)
        self.assertFalse(success)
        self.assertIn("Error exporting JSON", stderr.getvalue())


class TestNetworkLayer(unittest.TestCase):
    """Tests for the low-level JSON HTTP helper."""

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_success(self, mock_urlopen: MagicMock) -> None:
        """A 200 response with valid JSON is parsed into a dictionary."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"drinks": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_json("https://example.com/api")
        self.assertEqual(result, {"drinks": []})
        request = mock_urlopen.call_args[0][0]
        self.assertIn("example.com/api", request.full_url)

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_non_200_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Non-200 status codes yield None without raising."""
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.read.return_value = b"boom"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("https://example.com/api"))

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_network_error_returns_none(
        self, mock_urlopen: MagicMock
    ) -> None:
        """URLError is reported to stderr and mapped to None."""
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_json("https://example.com/api")
        self.assertIsNone(result)
        self.assertIn("Error requesting https://example.com/api", stderr.getvalue())

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_malformed_payload_returns_none(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Invalid JSON payloads are treated as fetch failures."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"not-json{"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("https://example.com/api"))

    @patch("main.fetch_json")
    def test_search_name_without_drinks_key(self, mock_fetch: MagicMock) -> None:
        """A null drinks payload maps to an empty result list."""
        mock_fetch.return_value = {"drinks": None}
        self.assertEqual(search_cocktail_by_name("zzz-not-a-drink"), [])

    @patch("main.fetch_json")
    def test_filter_ingredient_failure_returns_empty(
        self, mock_fetch: MagicMock
    ) -> None:
        """Network failures during ingredient filtering return no drinks."""
        mock_fetch.return_value = None
        self.assertEqual(filter_cocktails_by_ingredient("gin"), [])


class TestCocktailDetails(unittest.TestCase):
    """Tests for ID-based drink lookups."""

    def setUp(self) -> None:
        self.drink = {
            "idDrink": "11007",
            "strDrink": "Margarita",
            "strInstructions": "Shake with ice.",
        }

    @patch("main.fetch_json")
    def test_get_cocktail_details(self, mock_fetch: MagicMock) -> None:
        """Lookup returns the first drink of the payload."""
        mock_fetch.return_value = {"drinks": [self.drink]}
        drink = get_cocktail_details("11007")
        self.assertEqual(drink["strDrink"], "Margarita")
        self.assertIn("lookup.php?i=11007", mock_fetch.call_args[0][0])

    @patch("main.fetch_json")
    def test_get_cocktail_details_missing(self, mock_fetch: MagicMock) -> None:
        """Unknown IDs map to None."""
        mock_fetch.return_value = None
        self.assertIsNone(get_cocktail_details("00000"))


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    def setUp(self) -> None:
        self.summary = {"idDrink": "11007", "strDrink": "Margarita"}
        self.detailed = {
            "idDrink": "11007",
            "strDrink": "Margarita",
            "strCategory": "Ordinary Drink",
            "strAlcoholic": "Alcoholic",
            "strGlass": "Cocktail glass",
            "strInstructions": "Shake with ice.",
            "strIngredient1": "Tequila",
            "strMeasure1": "1 1/2 oz",
        }

    def _run_cli(self, *args: str) -> Any:
        """Run main() with patched argv; capture streams and exit code."""
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code: Any = None
        argv = ["main.py"] + list(args)
        with redirect_stdout(stdout), redirect_stderr(stderr), patch("sys.argv", argv):
            try:
                main()
            except SystemExit as exc:
                exit_code = exc.code
        return stdout.getvalue(), stderr.getvalue(), exit_code

    @patch("main.fetch_json")
    def test_cli_name_search_prints_card(self, mock_fetch: MagicMock) -> None:
        """--name prints a formatted recipe card for the match."""
        mock_fetch.return_value = {"drinks": [self.detailed]}
        stdout, _, code = self._run_cli("--name", "margarita")
        self.assertIsNone(code)
        self.assertIn("COCKTAIL RECIPE: MARGARITA", stdout)
        self.assertIn("1 1/2 oz Tequila", stdout)

    @patch("main.fetch_json")
    def test_cli_name_search_no_results(self, mock_fetch: MagicMock) -> None:
        """Empty search results exit 1 with an error message."""
        mock_fetch.return_value = {"drinks": None}
        _, stderr, code = self._run_cli("--name", "zzz-nope")
        self.assertEqual(code, 1)
        self.assertIn("No cocktails found matching your query.", stderr)

    @patch("main.fetch_json")
    def test_cli_random_prints_card(self, mock_fetch: MagicMock) -> None:
        """--random fetches and renders one random recipe card."""
        mock_fetch.return_value = {"drinks": [self.detailed]}
        stdout, _, code = self._run_cli("--random")
        self.assertIsNone(code)
        self.assertIn("COCKTAIL RECIPE: MARGARITA", stdout)
        self.assertIn("random.php", mock_fetch.call_args[0][0])

    @patch("main.fetch_json")
    def test_cli_ingredient_fetches_top_details(self, mock_fetch: MagicMock) -> None:
        """--ingredient lists other matches after the detailed top result."""
        summaries = [
            self.summary,
            {"idDrink": "11008", "strDrink": "Daiquiri"},
        ]
        mock_fetch.side_effect = [
            {"drinks": summaries},
            {"drinks": [self.detailed]},
        ]
        stdout, _, code = self._run_cli("--ingredient", "tequila")
        self.assertIsNone(code)
        self.assertIn("COCKTAIL RECIPE: MARGARITA", stdout)
        self.assertIn("Other matching drinks (1):", stdout)
        self.assertIn("Daiquiri (ID: 11008)", stdout)

    @patch("main.fetch_json")
    def test_cli_ingredient_no_results(self, mock_fetch: MagicMock) -> None:
        """Unknown ingredients exit 1 without printing a card."""
        mock_fetch.return_value = {"drinks": None}
        _, stderr, code = self._run_cli("--ingredient", "kryptonite")
        self.assertEqual(code, 1)
        self.assertIn("No cocktails found matching your query.", stderr)

    @patch("main.fetch_json")
    def test_cli_export_json(self, mock_fetch: MagicMock) -> None:
        """--json writes the matched recipes to disk."""
        mock_fetch.return_value = {"drinks": [self.detailed]}
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "recipes.json")
            stdout, _, code = self._run_cli("--name", "margarita", "--json", out_path)
            self.assertIsNone(code)
            self.assertIn("Exported 1 recipe(s)", stdout)
            data = json.loads(Path(out_path).read_text(encoding="utf-8"))
        self.assertEqual(data[0]["name"], "Margarita")
        self.assertEqual(data[0]["ingredients"], ["1 1/2 oz Tequila"])


if __name__ == "__main__":
    unittest.main()

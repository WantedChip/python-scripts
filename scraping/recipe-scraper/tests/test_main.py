"""Unit tests for Recipe Scraper."""

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from typing import Any, List
from unittest.mock import MagicMock, patch

from main import (
    Recipe,
    build_parser,
    extract_recipe,
    fallback_html_recipe_parser,
    find_recipe_json_ld,
    load_input_html,
    main,
    parse_iso_duration,
    parse_recipe_from_json_ld,
    recipe_to_markdown,
)


def _urlopen_result(payload: str, status: int = 200) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = payload.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


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


class TestParseIsoDurationExtra(unittest.TestCase):
    """Additional duration formatting branches."""

    def test_pluralisation_and_empty_values(self) -> None:
        self.assertEqual(parse_iso_duration("PT2H"), "2 hrs")
        self.assertEqual(parse_iso_duration("P2DT1M"), "2 days 1 min")
        self.assertEqual(parse_iso_duration(""), "")
        self.assertEqual(parse_iso_duration("PT"), "PT")

    def test_seconds_only_durations_pass_through_unchanged(self) -> None:
        self.assertEqual(parse_iso_duration("PT45S"), "PT45S")


class TestFindRecipeJsonLdSearch(unittest.TestCase):
    """Recursive Recipe object discovery inside JSON-LD payloads."""

    def test_malformed_or_empty_scripts_are_skipped(self) -> None:
        html = (
            "<script type='application/ld+json'></script>"
            "<script type='application/ld+json'>{nope}</script>"
        )
        self.assertIsNone(find_recipe_json_ld(html))

    def test_unparseable_input_returns_none(self) -> None:
        self.assertIsNone(find_recipe_json_ld(None))

    def test_recipe_nested_in_graph_is_found(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@context": "https://schema.org",
         "@graph": [
            {"@type": "WebPage", "name": "Blog"},
            {"@type": "Recipe", "name": "Deep Recipe"}
         ]}
        </script>
        """
        found = find_recipe_json_ld(html)
        assert found is not None
        self.assertEqual(found["name"], "Deep Recipe")

    def test_list_typed_recipe_node_matches(self) -> None:
        html = (
            '<script type="application/ld+json">'
            + json.dumps({"@type": ["CreativeWork", "Recipe"], "name": "List Typed"})
            + "</script>"
        )
        found = find_recipe_json_ld(html)
        assert found is not None
        self.assertEqual(found["name"], "List Typed")

    def test_bare_json_without_script_tags_is_ignored(self) -> None:
        data = json.dumps({"@type": "Recipe", "name": "No Script"})
        self.assertIsNone(find_recipe_json_ld(data))

    def test_no_recipe_returns_none(self) -> None:
        data = {"@type": "Article", "name": "Not food"}
        self.assertIsNone(find_recipe_json_ld(json.dumps(data)))


class TestParseRecipeFromJsonLdVariants(unittest.TestCase):
    """Field-level fallbacks of the JSON-LD recipe mapper."""

    def test_dict_wrapped_title_description_and_authors(self) -> None:
        data = {
            "@type": "Recipe",
            "name": {"text": "Wrapped Title"},
            "description": {"text": "Wrapped description"},
            "author": [
                {"name": "Chef Ada"},
                {"name": "Chef Bob"},
            ],
            "totalTime": "P1DT2H",
        }
        recipe = parse_recipe_from_json_ld(data)
        self.assertEqual(recipe.title, "Wrapped Title")
        self.assertEqual(recipe.description, "Wrapped description")
        self.assertEqual(recipe.author, "Chef Ada")
        self.assertEqual(recipe.total_time, "1 day 2 hrs")

    def test_author_string_form(self) -> None:
        recipe = parse_recipe_from_json_ld({"author": "Grandma"})
        self.assertEqual(recipe.author, "Grandma")

    def test_yield_list_joined_with_commas(self) -> None:
        recipe = parse_recipe_from_json_ld({"recipeYield": ["2 loaves", "12 rolls"]})
        self.assertEqual(recipe.yield_amount, "2 loaves, 12 rolls")

    def test_ingredients_as_multiline_string_split_on_newlines(self) -> None:
        recipe = parse_recipe_from_json_ld(
            {"recipeIngredient": "2 cups flour\n\n1 tsp salt"}
        )
        self.assertEqual(recipe.ingredients, ["2 cups flour", "1 tsp salt"])

    def test_instructions_as_plain_multiline_string(self) -> None:
        recipe = parse_recipe_from_json_ld(
            {"recipeInstructions": "Boil water.\n\nAdd pasta."}
        )
        self.assertEqual(recipe.instructions, ["Boil water.", "Add pasta."])

    def test_image_shapes_str_list_of_str_list_of_dict_and_dict(self) -> None:
        self.assertEqual(
            parse_recipe_from_json_ld({"image": "a.jpg"}).image_url, "a.jpg"
        )
        self.assertEqual(
            parse_recipe_from_json_ld({"image": ["b.jpg"]}).image_url, "b.jpg"
        )
        self.assertEqual(
            parse_recipe_from_json_ld({"image": [{"url": "c.jpg"}]}).image_url,
            "c.jpg",
        )
        self.assertEqual(
            parse_recipe_from_json_ld({"image": {"url": "d.jpg"}}).image_url, "d.jpg"
        )

    def test_howto_sections_expand_into_numbered_steps(self) -> None:
        data = {
            "@type": "Recipe",
            "name": "Sectioned",
            "recipeInstructions": [
                {"@type": "HowToStep", "text": "Preheat oven."},
                {
                    "@type": "HowToSection",
                    "name": "Frosting",
                    "itemListElement": [
                        {"@type": "HowToStep", "text": "Beat butter."},
                    ],
                },
                {"@type": "HowToStep", "name": "Named-only step"},
                {"unknown_type": True, "text": "Generic step text"},
            ],
        }
        recipe = parse_recipe_from_json_ld(data)
        self.assertEqual(
            recipe.instructions,
            [
                "Preheat oven.",
                "### Frosting",
                "Beat butter.",
                "Named-only step",
                "Generic step text",
            ],
        )

    def test_to_dict_contains_all_fields(self) -> None:
        recipe = Recipe(title="T")
        as_dict: Any = recipe.to_dict()
        self.assertEqual(set(as_dict.keys()), set(Recipe.__dataclass_fields__.keys()))


class TestFallbackHtmlParser(unittest.TestCase):
    """Heuristic HTML parsing for pages without JSON-LD."""

    FULL_PAGE = """
    <html><body>
    <h1>Homemade Salsa</h1>
    <h2>Ingredients</h2>
    <ul class="ingredient-list">
        <li>4 ripe tomatoes</li>
        <li>1 onion</li>
        <li>%s</li>
    </ul>
    <h2>Directions</h2>
    <ol class="instructions">
        <li>Chop the tomatoes.</li>
        <li>Dice the onion.</li>
    </ol>
    </body></html>
    """

    def test_full_page_extraction(self) -> None:
        filler = "x" * 200
        recipe = fallback_html_recipe_parser(self.FULL_PAGE % filler)
        self.assertEqual(recipe.title, "Homemade Salsa")
        self.assertEqual(recipe.ingredients, ["4 ripe tomatoes", "1 onion"])
        self.assertEqual(recipe.instructions, ["Chop the tomatoes.", "Dice the onion."])

    def test_section_based_ingredient_block(self) -> None:
        html = (
            "<html><body><section class='ingredients'><ul>"
            "<li>1 lime</li><li>Cilantro</li></ul></section></body></html>"
        )
        recipe = fallback_html_recipe_parser(html)
        self.assertIn("1 lime", recipe.ingredients)

    def test_div_step_fallback_for_instructions(self) -> None:
        html = (
            "<html><body><div class='step-by-step'>"
            "<p>Mix everything.</p><p>Serve chilled.</p></div></body></html>"
        )
        recipe = fallback_html_recipe_parser(html)
        self.assertEqual(recipe.instructions, ["Mix everything.", "Serve chilled."])

    def test_missing_title_defaults_to_placeholder(self) -> None:
        recipe = fallback_html_recipe_parser("<html><body><p>No h1</p></body></html>")
        self.assertEqual(recipe.title, "Untitled Recipe")

    def test_extract_recipe_routes_to_fallback_without_json_ld(self) -> None:
        recipe = extract_recipe("<html><body><h1>Fallback Stew</h1></body></html>")
        self.assertEqual(recipe.title, "Fallback Stew")


class TestMarkdownFormatting(unittest.TestCase):
    """recipe_to_markdown rendering branches."""

    def test_complete_recipe_card(self) -> None:
        recipe = Recipe(
            title="Tea",
            description="A warm cup.",
            author="Brewer",
            prep_time="5 mins",
            cook_time="10 mins",
            total_time="15 mins",
            yield_amount="2 cups",
            ingredients=["Water", "Tea leaves"],
            instructions=["### Steeping", "Boil water.", "Add leaves."],
        )
        md = recipe_to_markdown(recipe)
        self.assertIn("*A warm cup.*", md)
        meta_line = (
            "**Author:** Brewer | **Prep Time:** 5 mins | "
            "**Cook Time:** 10 mins | **Total Time:** 15 mins | "
            "**Yield:** 2 cups"
        )
        self.assertIn(meta_line, md)
        self.assertIn("- Water", md)
        self.assertIn("\n### Steeping\n", md)
        self.assertIn("1. Boil water.", md)
        self.assertIn("2. Add leaves.", md)

    def test_minimal_recipe_uses_placeholders(self) -> None:
        md = recipe_to_markdown(Recipe(title="Empty"))
        self.assertIn("# Empty", md)
        self.assertIn("*No ingredients listed.*", md)
        self.assertIn("*No instructions listed.*", md)
        self.assertNotIn("**Author:**", md)


class TestLoadInputHtml(unittest.TestCase):
    """Local file and remote URL loading."""

    def test_local_file_is_read_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "page.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write("<html><h1>Local</h1></html>")
            self.assertIn("Local", load_input_html(path))

    def test_remote_url_is_fetched_via_urlopen(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            return_value=_urlopen_result("<html><h1>Remote</h1></html>"),
        ) as mock_open:
            body = load_input_html("https://recipes.example.com/tea")
        self.assertIn("Remote", body)
        req = mock_open.call_args.args[0]
        self.assertEqual(req.full_url, "https://recipes.example.com/tea")


class TestRecipeCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    SAMPLE_HTML = """
    <html><head>
    <script type="application/ld+json">
    {"@type": "Recipe", "name": "CLI Soup",
     "recipeIngredient": ["2 carrots"],
     "recipeInstructions": ["Chop carrots.", "Simmer 20 minutes."]}
    </script>
    </head><body></body></html>
    """

    def test_build_parser_defaults(self) -> None:
        args = build_parser().parse_args(["src.html"])
        self.assertEqual(args.format, "markdown")
        self.assertIsNone(args.output)

    def _run_main(self, argv: List[str]) -> tuple:
        """Run main() capturing stdout/stderr; return (code, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_main_local_file_prints_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "soup.html")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(self.SAMPLE_HTML)
            code, out, _ = self._run_main([src_path])
        self.assertEqual(code, 0)
        self.assertIn("# CLI Soup", out)
        self.assertIn("- 2 carrots", out)
        self.assertIn("1. Chop carrots.", out)

    def test_main_local_file_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "soup.html")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(self.SAMPLE_HTML)
            code, out, _ = self._run_main([src_path, "--format", "json"])
        self.assertEqual(code, 0)
        payload: Any = json.loads(out)
        self.assertEqual(payload["title"], "CLI Soup")
        self.assertEqual(payload["ingredients"], ["2 carrots"])

    def test_main_url_source_saves_both_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = os.path.join(tmpdir, "out")
            argv = [
                "https://recipes.example.com/soup",
                "--format",
                "both",
                "--output",
                base,
            ]
            with patch(
                "main.urllib.request.urlopen",
                return_value=_urlopen_result(self.SAMPLE_HTML),
            ):
                code, out, _ = self._run_main(argv)
            self.assertEqual(code, 0)
            self.assertIn(f"Recipe saved to {base}.md", out)
            self.assertIn(f"Recipe JSON saved to {base}.json", out)
            with open(f"{base}.md", encoding="utf-8") as f:
                self.assertIn("# CLI Soup", f.read())
            with open(f"{base}.json", encoding="utf-8") as f:
                saved: Any = json.load(f)
            self.assertEqual(saved["title"], "CLI Soup")

    def test_main_output_extension_appended_for_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "soup.html")
            base = os.path.join(tmpdir, "card")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(self.SAMPLE_HTML)
            code, out, _ = self._run_main([src_path, "--output", base])
            self.assertEqual(code, 0)
            self.assertIn(f"Recipe saved to {base}.md", out)
            self.assertTrue(os.path.exists(f"{base}.md"))

    def test_main_url_error_returns_exit_code_one(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        ):
            code, _, err = self._run_main(["https://recipes.example.com/x"])
        self.assertEqual(code, 1)
        self.assertIn("Error loading source", err)


if __name__ == "__main__":
    unittest.main()

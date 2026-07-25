#!/usr/bin/env python3
"""Cocktail Recipe Fetcher script.

Searches cocktail recipes by name or ingredient, or fetches random
recipes using TheCocktailDB API.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, cast

COCKTAIL_API_BASE = "https://www.thecocktaildb.com/api/json/v1/1"


def fetch_json(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Fetch JSON data from a URL using urllib.

    Args:
        url: The endpoint URL.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON object or None on error.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "CocktailRecipeFetcher/1.0 (Python)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                return cast(Dict[str, Any], json.loads(response.read().decode("utf-8")))
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error requesting {url}: {err}", file=sys.stderr)
    return None


def search_cocktail_by_name(name: str) -> List[Dict[str, Any]]:
    """Search cocktails by drink name.

    Args:
        name: Name or partial name of the cocktail.

    Returns:
        List of matching drink dictionaries.
    """
    query = urllib.parse.quote(name.strip())
    url = f"{COCKTAIL_API_BASE}/search.php?s={query}"
    res = fetch_json(url)
    return res.get("drinks") or [] if res else []


def filter_cocktails_by_ingredient(ingredient: str) -> List[Dict[str, Any]]:
    """Filter cocktails by ingredient name.

    Args:
        ingredient: Ingredient name (e.g. Gin, Tequila).

    Returns:
        List of summarized drink dictionaries.
    """
    query = urllib.parse.quote(ingredient.strip())
    url = f"{COCKTAIL_API_BASE}/filter.php?i={query}"
    res = fetch_json(url)
    return res.get("drinks") or [] if res else []


def get_random_cocktail() -> Optional[Dict[str, Any]]:
    """Fetch a single random cocktail recipe.

    Returns:
        Drink detail dictionary or None.
    """
    url = f"{COCKTAIL_API_BASE}/random.php"
    res = fetch_json(url)
    drinks = res.get("drinks") if res else None
    return drinks[0] if drinks else None


def get_cocktail_details(drink_id: str) -> Optional[Dict[str, Any]]:
    """Lookup complete details for a drink by ID.

    Args:
        drink_id: Unique drink ID string.

    Returns:
        Drink detail dictionary or None.
    """
    url = f"{COCKTAIL_API_BASE}/lookup.php?i={drink_id}"
    res = fetch_json(url)
    drinks = res.get("drinks") if res else None
    return drinks[0] if drinks else None


def extract_ingredients(drink: Dict[str, Any]) -> List[str]:
    """Extract non-empty ingredients and measures from a drink dictionary.

    Args:
        drink: Raw drink payload dictionary from API.

    Returns:
        Formatted list of ingredient lines (e.g. "2 oz Gin").
    """
    ingredients: List[str] = []
    for i in range(1, 16):
        ing = drink.get(f"strIngredient{i}")
        meas = drink.get(f"strMeasure{i}")
        if ing and ing.strip():
            meas_str = f"{meas.strip()} " if meas and meas.strip() else ""
            ingredients.append(f"{meas_str}{ing.strip()}")
    return ingredients


def format_recipe_card(drink: Dict[str, Any]) -> str:
    """Format cocktail recipe into a terminal card display.

    Args:
        drink: Drink payload dictionary.

    Returns:
        Formatted ASCII string representation of cocktail recipe.
    """
    title = drink.get("strDrink", "Unknown Drink")
    category = drink.get("strCategory", "Uncategorized")
    alcoholic = drink.get("strAlcoholic", "Unknown")
    glass = drink.get("strGlass", "Standard Glass")
    instructions = drink.get("strInstructions", "No instructions provided.").strip()
    thumb = drink.get("strDrinkThumb", "N/A")

    ingredients = extract_ingredients(drink)
    ing_formatted = (
        "\n".join([f"  • {item}" for item in ingredients])
        if ingredients
        else "  (No ingredients listed)"
    )

    lines = [
        "==================================================",
        f"  COCKTAIL RECIPE: {title.upper()}",
        "==================================================",
        f"  Category   : {category}",
        f"  Alcoholic  : {alcoholic}",
        f"  Glass      : {glass}",
        "--------------------------------------------------",
        "  INGREDIENTS:",
        ing_formatted,
        "--------------------------------------------------",
        "  INSTRUCTIONS:",
        f"  {instructions}",
        "--------------------------------------------------",
        f"  Image URL  : {thumb}",
        "==================================================",
    ]
    return "\n".join(lines)


def export_json(drinks: List[Dict[str, Any]], filepath: str) -> bool:
    """Export formatted list of drinks to a JSON file.

    Args:
        drinks: List of drink dictionaries.
        filepath: Target output file path.

    Returns:
        True if export succeeded, False otherwise.
    """
    export_list = []
    for d in drinks:
        export_list.append(
            {
                "id": d.get("idDrink"),
                "name": d.get("strDrink"),
                "category": d.get("strCategory"),
                "alcoholic": d.get("strAlcoholic"),
                "glass": d.get("strGlass"),
                "ingredients": extract_ingredients(d),
                "instructions": d.get("strInstructions"),
                "image_url": d.get("strDrinkThumb"),
            }
        )

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_list, f, indent=2)
        return True
    except OSError as err:
        print(f"Error exporting JSON to {filepath}: {err}", file=sys.stderr)
        return False


def main() -> None:  # pylint: disable=too-many-branches
    """Main CLI entrypoint for Cocktail Recipe Fetcher."""
    parser = argparse.ArgumentParser(
        description="Search cocktail recipes using TheCocktailDB API."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--name", "-n", help="Search cocktail by name (e.g. Margarita)")
    group.add_argument(
        "--ingredient", "-i", help="Filter cocktails by ingredient (e.g. Gin)"
    )
    group.add_argument(
        "--random", "-r", action="store_true", help="Fetch a random cocktail recipe"
    )

    parser.add_argument("--json", "-j", help="Export matching recipe(s) to JSON file")

    args = parser.parse_args()

    results: List[Dict[str, Any]] = []

    if args.random:
        print("Fetching random cocktail...")
        drink = get_random_cocktail()
        if drink:
            results.append(drink)
    elif args.name:
        print(f"Searching cocktail recipes matching '{args.name}'...")
        results = search_cocktail_by_name(args.name)
    elif args.ingredient:
        print(f"Finding cocktails containing ingredient '{args.ingredient}'...")
        summaries = filter_cocktails_by_ingredient(args.ingredient)
        if summaries:
            print(
                f"Found {len(summaries)} drinks. Fetching details for the top result..."
            )
            top_detail = get_cocktail_details(summaries[0]["idDrink"])
            if top_detail:
                results.append(top_detail)
            # Add remaining basic summaries to results for listing/export
            results.extend(summaries[1:])

    if not results:
        print("No cocktails found matching your query.", file=sys.stderr)
        sys.exit(1)

    # Print main recipe card for the first result
    first_drink = results[0]
    if "strInstructions" not in first_drink and "idDrink" in first_drink:
        # Fetch detailed drink info if only summary was retrieved
        detailed = get_cocktail_details(first_drink["idDrink"])
        if detailed:
            first_drink = detailed
            results[0] = detailed

    print(format_recipe_card(first_drink))

    if len(results) > 1:
        print(f"\nOther matching drinks ({len(results) - 1}):")
        for d in results[1:10]:
            print(f"  • {d.get('strDrink')} (ID: {d.get('idDrink')})")

    if args.json:
        if export_json(results, args.json):
            print(f"Exported {len(results)} recipe(s) to {args.json}")


if __name__ == "__main__":
    main()

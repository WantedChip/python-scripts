"""Recipe Scraper.

Extracts recipe ingredients, quantities, preparation times, yield, and
instructions from web pages or local HTML files using Schema.org JSON-LD or
HTML tag heuristics.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import html.parser
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Recipe:
    """Dataclass representing extracted recipe details."""

    title: str
    description: str = ""
    author: str = ""
    prep_time: str = ""
    cook_time: str = ""
    total_time: str = ""
    yield_amount: str = ""
    ingredients: List[str] = field(default_factory=list)
    instructions: List[str] = field(default_factory=list)
    image_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert recipe to dictionary format."""
        return asdict(self)


def parse_iso_duration(duration: str) -> str:
    """Convert ISO 8601 duration format (e.g., PT1H30M) into human readable text.

    Args:
        duration: ISO 8601 duration string (e.g. PT20M).

    Returns:
        Formatted time string (e.g. "1 hr 30 mins").
    """
    if not duration or not duration.startswith("P"):
        return duration or ""

    pattern = (
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?"
        r"(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?"
    )
    match = re.match(pattern, duration)
    if not match:
        return duration

    parts = []
    days = match.group("days")
    hours = match.group("hours")
    minutes = match.group("minutes")

    if days:
        parts.append(f"{days} day{'s' if int(days) > 1 else ''}")
    if hours:
        parts.append(f"{hours} hr{'s' if int(hours) > 1 else ''}")
    if minutes:
        parts.append(f"{minutes} min{'s' if int(minutes) > 1 else ''}")

    return " ".join(parts) if parts else duration


class JSONLDExtractor(html.parser.HTMLParser):
    """HTML Parser subclass to find and extract JSON-LD script elements."""

    def __init__(self) -> None:
        super().__init__()
        self.in_json_ld = False
        self.json_scripts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() == "script":
            attr_dict = {k: v or "" for k, v in attrs}
            if attr_dict.get("type", "").lower() == "application/ld+json":
                self.in_json_ld = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.in_json_ld:
            self.in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self.in_json_ld:
            self.json_scripts.append(data.strip())


def find_recipe_json_ld(html_content: str) -> Optional[Dict[str, Any]]:
    """Locate and extract Schema.org/Recipe JSON-LD structure from HTML.

    Args:
        html_content: Raw HTML text string.

    Returns:
        Dictionary representing the Recipe schema or None if not found.
    """
    parser = JSONLDExtractor()
    try:
        parser.feed(html_content)
    except (ValueError, TypeError, KeyError, AttributeError):
        pass

    for script_text in parser.json_scripts:
        if not script_text:
            continue
        try:
            data = json.loads(script_text)
            recipe_obj = _search_for_recipe_object(data)
            if recipe_obj:
                return recipe_obj
        except json.JSONDecodeError:
            continue

    return None


def _search_for_recipe_object(data: Any) -> Optional[Dict[str, Any]]:
    """Recursively search for @type == Recipe in JSON-LD structure.

    Args:
        data: Parsed JSON data (dict, list, etc.).

    Returns:
        Recipe dict if found, None otherwise.
    """
    if isinstance(data, dict):
        type_val = data.get("@type", "")
        is_recipe = type_val == "Recipe" or (
            isinstance(type_val, list) and "Recipe" in type_val
        )
        if is_recipe:
            return data
        if "@graph" in data and isinstance(data["@graph"], list):
            return _search_for_recipe_object(data["@graph"])
        for _, val in data.items():
            result = _search_for_recipe_object(val)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _search_for_recipe_object(item)
            if result:
                return result
    return None


def parse_recipe_from_json_ld(data: Dict[str, Any]) -> Recipe:
    """Parse raw JSON-LD Recipe dictionary into a Recipe dataclass.

    Args:
        data: Dictionary of Schema.org Recipe data.

    Returns:
        Populated Recipe instance.
    """
    title = data.get("name", "Untitled Recipe")
    if isinstance(title, dict):
        title = title.get("text", "Untitled Recipe")

    description = data.get("description", "")
    if isinstance(description, dict):
        description = description.get("text", "")

    author = ""
    author_obj = data.get("author")
    if isinstance(author_obj, dict):
        author = author_obj.get("name", "")
    elif isinstance(author_obj, list) and author_obj:
        first = author_obj[0]
        author = first.get("name", "") if isinstance(first, dict) else str(first)
    elif isinstance(author_obj, str):
        author = author_obj

    prep_time = parse_iso_duration(str(data.get("prepTime", "")))
    cook_time = parse_iso_duration(str(data.get("cookTime", "")))
    total_time = parse_iso_duration(str(data.get("totalTime", "")))

    yield_val = data.get("recipeYield", "")
    if isinstance(yield_val, list):
        yield_amount = ", ".join(str(y) for y in yield_val)
    else:
        yield_amount = str(yield_val)

    # Ingredients extraction
    raw_ingredients = data.get("recipeIngredient", [])
    ingredients = []
    if isinstance(raw_ingredients, list):
        for item in raw_ingredients:
            if isinstance(item, str):
                ingredients.append(item.strip())
    elif isinstance(raw_ingredients, str):
        ingredients = [i.strip() for i in raw_ingredients.split("\n") if i.strip()]

    # Instructions extraction
    raw_instructions = data.get("recipeInstructions", [])
    instructions = _parse_instructions(raw_instructions)

    # Image URL
    image_url = ""
    image_obj = data.get("image")
    if isinstance(image_obj, str):
        image_url = image_obj
    elif isinstance(image_obj, list) and image_obj:
        first_img = image_obj[0]
        if isinstance(first_img, str):
            image_url = first_img
        elif isinstance(first_img, dict):
            image_url = first_img.get("url", "")
    elif isinstance(image_obj, dict):
        image_url = image_obj.get("url", "")

    return Recipe(
        title=title.strip(),
        description=description.strip(),
        author=author.strip(),
        prep_time=prep_time,
        cook_time=cook_time,
        total_time=total_time,
        yield_amount=yield_amount,
        ingredients=ingredients,
        instructions=instructions,
        image_url=image_url,
    )


def _parse_instructions(raw_instructions: Any) -> List[str]:
    """Helper to parse instructions from string or structures."""
    instructions: List[str] = []
    if isinstance(raw_instructions, str):
        return [s.strip() for s in raw_instructions.split("\n") if s.strip()]

    if isinstance(raw_instructions, list):
        for item in raw_instructions:
            if isinstance(item, str):
                if item.strip():
                    instructions.append(item.strip())
            elif isinstance(item, dict):
                item_type = item.get("@type", "")
                if item_type == "HowToStep":
                    text = item.get("text") or item.get("name") or ""
                    if text.strip():
                        instructions.append(text.strip())
                elif item_type == "HowToSection":
                    section_name = item.get("name")
                    if section_name:
                        instructions.append(f"### {section_name}")
                    sub_steps = item.get("itemListElement", [])
                    instructions.extend(_parse_instructions(sub_steps))
                else:
                    text = item.get("text") or item.get("name") or ""
                    if text.strip():
                        instructions.append(text.strip())
    return instructions


def fallback_html_recipe_parser(html_content: str) -> Recipe:
    """Fallback HTML tag heuristic parser for pages lacking JSON-LD.

    Args:
        html_content: Raw HTML content.

    Returns:
        Recipe dataclass with parsed elements.
    """
    h1_pat = r"<h1[^>]*>(.*?)</h1>"
    title_match = re.search(h1_pat, html_content, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
    else:
        title = "Untitled Recipe"

    # Extract ingredients matching li elements near ingredient keywords
    ingredients: List[str] = []
    ing_pat = r"(<ul[^>]*class=[\"'][^\"']*ingredient[^\"']*[\"'][^>]*>.*?</ul>)"
    ing_block = re.search(ing_pat, html_content, re.IGNORECASE | re.DOTALL)
    if not ing_block:
        sec_pat = r"(<section[^>]*ingredient.*?</section>)"
        ing_block = re.search(sec_pat, html_content, re.IGNORECASE | re.DOTALL)

    target_text = ing_block.group(1) if ing_block else html_content
    li_matches = re.findall(
        r"<li[^>]*>(.*?)</li>", target_text, re.IGNORECASE | re.DOTALL
    )
    for li in li_matches:
        clean_text = re.sub(r"<[^>]+>", "", li).strip()
        if clean_text and len(clean_text) < 150:
            ingredients.append(clean_text)

    # Instructions fallback
    instructions: List[str] = []
    inst_pat = (
        r"(<ol[^>]*class=[\"'][^\"']*(?:instruction|step)[^\"']*[\"'][^>]*>"
        r".*?</ol>)"
    )
    inst_block = re.search(inst_pat, html_content, re.IGNORECASE | re.DOTALL)
    if not inst_block:
        div_pat = (
            r"(<div[^>]*class=[\"'][^\"']*(?:instruction|step)[^\"']*[\"']"
            r"[^>]*>.*?</div>)"
        )
        inst_block = re.search(div_pat, html_content, re.IGNORECASE | re.DOTALL)

    inst_text = inst_block.group(1) if inst_block else ""
    if inst_text:
        st_pat = r"<(?:li|p)[^>]*>(.*?)</(?:li|p)>"
        step_matches = re.findall(st_pat, inst_text, re.IGNORECASE | re.DOTALL)
        for step in step_matches:
            clean_step = re.sub(r"<[^>]+>", "", step).strip()
            if clean_step:
                instructions.append(clean_step)

    return Recipe(
        title=title,
        ingredients=ingredients,
        instructions=instructions,
    )


def extract_recipe(html_content: str) -> Recipe:
    """Extract recipe details from HTML using JSON-LD or HTML fallbacks.

    Args:
        html_content: Raw HTML text string.

    Returns:
        Extracted Recipe object.
    """
    json_ld_data = find_recipe_json_ld(html_content)
    if json_ld_data:
        return parse_recipe_from_json_ld(json_ld_data)
    return fallback_html_recipe_parser(html_content)


def recipe_to_markdown(recipe: Recipe) -> str:
    """Format a Recipe dataclass into Markdown recipe card format.

    Args:
        recipe: Recipe dataclass.

    Returns:
        Formatted Markdown text.
    """
    md = [f"# {recipe.title}", ""]
    if recipe.description:
        md.extend([f"*{recipe.description}*", ""])

    meta = []
    if recipe.author:
        meta.append(f"**Author:** {recipe.author}")
    if recipe.prep_time:
        meta.append(f"**Prep Time:** {recipe.prep_time}")
    if recipe.cook_time:
        meta.append(f"**Cook Time:** {recipe.cook_time}")
    if recipe.total_time:
        meta.append(f"**Total Time:** {recipe.total_time}")
    if recipe.yield_amount:
        meta.append(f"**Yield:** {recipe.yield_amount}")

    if meta:
        md.extend([" | ".join(meta), "", "---", ""])

    md.extend(["## Ingredients", ""])
    if recipe.ingredients:
        for ing in recipe.ingredients:
            md.append(f"- {ing}")
    else:
        md.append("*No ingredients listed.*")

    md.extend(["", "## Instructions", ""])
    if recipe.instructions:
        step_num = 1
        for inst in recipe.instructions:
            if inst.startswith("### "):
                md.extend(["", inst, ""])
            else:
                md.append(f"{step_num}. {inst}")
                step_num += 1
    else:
        md.append("*No instructions listed.*")

    return "\n".join(md)


def load_input_html(target: str) -> str:
    """Load HTML content from web URL or local file path.

    Args:
        target: URL or local file path string.

    Returns:
        HTML string content.
    """
    if os.path.exists(target):
        with open(target, "r", encoding="utf-8") as f:
            return f.read()

    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) RecipeScraper/1.0")
    }
    req = urllib.request.Request(target, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:  # nosec B310
        body = response.read().decode("utf-8", errors="ignore")
        return str(body)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Extract recipe ingredients, timing, and instructions from web "
        "pages or HTML files."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("source", type=str, help="URL or local HTML file path")
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file path base (without extension if using both)",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Recipe Scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    try:
        html_content = load_input_html(parsed.source)
    except (urllib.error.URLError, OSError, ValueError) as err:
        print(f"Error loading source '{parsed.source}': {err}", file=sys.stderr)
        return 1

    recipe = extract_recipe(html_content)

    md_content = recipe_to_markdown(recipe)
    json_content = json.dumps(recipe.to_dict(), indent=2)

    if parsed.output:
        base_path = parsed.output
        if parsed.format in ["markdown", "both"]:
            md_path = base_path if base_path.endswith(".md") else f"{base_path}.md"
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            print(f"Recipe saved to {md_path}")
        if parsed.format in ["json", "both"]:
            json_path = (
                base_path if base_path.endswith(".json") else f"{base_path}.json"
            )
            with open(json_path, "w", encoding="utf-8") as f:
                f.write(json_content)
            print(f"Recipe JSON saved to {json_path}")
    else:
        if parsed.format == "json":
            print(json_content)
        else:
            print(md_content)

    return 0


if __name__ == "__main__":
    sys.exit(main())

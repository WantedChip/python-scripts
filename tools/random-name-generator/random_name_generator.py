"""Random Name Generator.

Generates names for people (fantasy, sci-fi, classic, modern),
projects (tech, creative, business), or pets (dog, cat, exotic),
with optional alliteration support.
"""

# pylint: disable=duplicate-code
import argparse
import json
import os
import random
import sys
from typing import Any, Dict, List, Optional, Set

# Built-in Word Pools and Name Lists
NAME_POOLS: Dict[str, Any] = {
    "people": {
        "fantasy": {
            "prefixes": ["El", "Ly", "Tho", "Va", "Aet", "Gwy", "Ze", "Fael", "Dar"],
            "suffixes": ["dor", "ra", "rin", "lius", "gorn", "wyn", "nis", "thas"],
        },
        "sci-fi": {
            "prefixes": [
                "Cy",
                "Ne",
                "Ka",
                "Xan",
                "Zor",
                "Trek",
                "Vex",
                "Nova",
                "Astro",
            ],
            "suffixes": ["on", "ax", "ix", "ton", "a", "tar", "sec", "tron"],
        },
        "classic": [
            "Alexander",
            "Elizabeth",
            "Charles",
            "Victoria",
            "William",
            "Margaret",
            "George",
            "Catherine",
            "Thomas",
            "Eleanor",
            "Arthur",
            "Mary",
        ],
        "modern": [
            "Liam",
            "Emma",
            "Noah",
            "Olivia",
            "Oliver",
            "Ava",
            "Elijah",
            "Isabella",
            "James",
            "Sophia",
            "Benjamin",
            "Mia",
            "Lucas",
            "Charlotte",
        ],
    },
    "projects": {
        "tech": {
            "prefixes": ["Py", "Cyber", "Syn", "Flux", "Byte", "Data", "Cloud", "Opti"],
            "suffixes": ["Net", "Flow", "Core", "Grid", "Code", "Sync", "Link", "Node"],
        },
        "creative": {
            "prefixes": [
                "Art",
                "Color",
                "Ink",
                "Muse",
                "Idea",
                "Novel",
                "Poem",
                "Draft",
            ],
            "suffixes": ["Paint", "Craft", "Write", "Forge", "Wave", "Spire", "Space"],
        },
        "business": {
            "prefixes": [
                "Strat",
                "Fin",
                "Apex",
                "Vanguard",
                "Synergy",
                "Growth",
                "Core",
            ],
            "suffixes": ["Corp", "Edge", "Partners", "Holdings", "Capital", "Group"],
        },
    },
    "pets": {
        "dog": ["Max", "Bella", "Charlie", "Luna", "Cooper", "Lucy", "Rocky", "Daisy"],
        "cat": ["Milo", "Luna", "Oliver", "Bella", "Leo", "Lily", "Simba", "Chloe"],
        "exotic": ["Spike", "Ziggy", "Rex", "Bubbles", "Gizmo", "Peanut", "Ninja"],
    },
}


def load_pools_database(custom_path: Optional[str]) -> Dict[str, Any]:
    """Loads word pools from custom JSON database or falls back to built-ins.

    Args:
        custom_path: Optional path to custom JSON database.

    Returns:
        Pool database dictionary.
    """
    if not custom_path:
        return NAME_POOLS

    if not os.path.exists(custom_path):
        print(
            f"Warning: Custom data path '{custom_path}' does not exist. "
            "Using built-in pools.",
            file=sys.stderr,
        )
        return NAME_POOLS

    try:
        with open(custom_path, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, ValueError) as err:
        print(
            f"Warning: Failed to parse custom names pools ({err}). "
            "Using built-in pools.",
            file=sys.stderr,
        )
    return NAME_POOLS


def generate_syllabic_name(
    prefixes: List[str], suffixes: List[str], alliterate_char: Optional[str] = None
) -> str:
    """Generates a pseudo-word from prefixes and suffixes with optional alliteration.

    Args:
        prefixes: List of starting syllables.
        suffixes: List of ending syllables.
        alliterate_char: Optional character to filter prefix list by.

    Returns:
        Generated syllabic word.
    """
    # Filter prefixes if alliteration is requested
    if alliterate_char:
        matching_prefixes = [
            p for p in prefixes if p.lower().startswith(alliterate_char.lower())
        ]
        # Fall back to all prefixes if no match
        pref_list = matching_prefixes if matching_prefixes else prefixes
    else:
        pref_list = prefixes

    pref = random.choice(pref_list)  # nosec B311
    suff = random.choice(suffixes)  # nosec B311
    return f"{pref}{suff}"


def generate_names(
    category: str,
    style: str,
    quantity: int,
    alliterate: bool = False,
    custom_path: Optional[str] = None,
) -> List[str]:
    """Generates a list of randomized names based on requested criteria.

    Args:
        category: Core category ('people', 'projects', 'pets').
        style: Subcategory style (e.g. 'fantasy', 'tech', 'dog').
        quantity: Count of names to generate.
        alliterate: Force matching first characters.
        custom_path: Optional custom database path.

    Returns:
        List of generated name strings.
    """
    # pylint: disable=too-many-locals,too-many-branches
    pools = load_pools_database(custom_path)

    cat_data = pools.get(category.lower())
    if not cat_data:
        return [f"Unknown-Category-Name-{i}" for i in range(1, quantity + 1)]

    style_data = cat_data.get(style.lower())
    if not style_data:
        # Fallback to general category pool list if style mismatch
        style_keys = list(cat_data.keys())
        fallback_style = style_keys[0] if style_keys else ""
        style_data = cat_data.get(fallback_style, [])

    generated: Set[str] = set()
    attempts = 0
    max_attempts = quantity * 10

    while len(generated) < quantity and attempts < max_attempts:
        attempts += 1
        name = ""

        # Check if list of pre-made names or prefix/suffix structures
        if isinstance(style_data, dict):
            # Syllable-based generation (fantasy, sci-fi, projects)
            prefixes = style_data.get("prefixes", ["Pro"])
            suffixes = style_data.get("suffixes", ["ject"])

            if alliterate:
                # Select a random letter from the first character of all prefixes
                chosen_char = random.choice(prefixes)[0].lower()  # nosec B311
                # Ensure prefix and suffix both alliterate if possible
                pref = generate_syllabic_name(prefixes, suffixes, chosen_char)
                # For project names, we can check if suffix starts with same char or not
                name = pref
            else:
                name = generate_syllabic_name(prefixes, suffixes)

        elif isinstance(style_data, list):
            # List-based generation (classic, modern, pet types)
            # If alliterate is requested, we can try to generate a double name
            # (e.g., Charles Arthur -> CA; for alliteration: Charlie Cooper -> CC)
            base_name = random.choice(style_data)  # nosec B311
            if alliterate:
                first_char = base_name[0].lower()
                # Find another word in pool with same first letter
                matches = [w for w in style_data if w[0].lower() == first_char]
                second_name = random.choice(matches)  # nosec B311
                name = f"{base_name} {second_name}"
            else:
                name = base_name

        if name:
            generated.add(name)

    # Ensure quantity is satisfied even if set is smaller due to pool duplicates
    results = list(generated)
    while len(results) < quantity:
        results.append(f"Generic-{category.title()}-{len(results)+1}")

    return results


def format_names_markdown(
    names: List[str], category: str, style: str, alliterate: bool
) -> str:
    """Formats list of names as a Markdown document.

    Args:
        names: List of generated name strings.
        category: Category selected.
        style: Sub-style chosen.
        alliterate: Indicates if alliteration is enforced.

    Returns:
        Formatted markdown.
    """
    md = []
    md.append("# Generated Suggestions")
    md.append("")
    allit_status = "Enabled" if alliterate else "Disabled"
    md.append(
        f"**Category**: {category.title()} | "
        f"**Style/Theme**: {style.title()} | "
        f"**Alliteration**: {allit_status}"
    )
    md.append("")
    md.append("---")
    md.append("")
    for name in names:
        md.append(f"- **{name}**")
    md.append("")
    return "\n".join(md)


def main() -> None:
    """CLI entry point for random-name-generator."""
    parser = argparse.ArgumentParser(
        description="Generate names for people, projects, and pets."
    )
    parser.add_argument(
        "-c",
        "--category",
        choices=["people", "projects", "pets"],
        default="projects",
        help="Core category (default: projects).",
    )
    parser.add_argument(
        "-s",
        "--style",
        default="tech",
        help="Subcategory style (e.g. fantasy, sci-fi, classic, tech, dog, cat).",
    )
    parser.add_argument(
        "-q",
        "--quantity",
        type=int,
        default=5,
        help="Number of names to generate (1 to 50, default: 5).",
    )
    parser.add_argument(
        "--alliterate",
        action="store_true",
        help="Enforce alliterative naming pattern.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output serialization format (default: markdown).",
    )
    parser.add_argument(
        "-o", "--output", help="Write suggestions to file instead of stdout."
    )
    parser.add_argument(
        "--custom-data",
        help="Path to custom JSON file containing word pools/lists.",
    )

    args = parser.parse_args()

    # Constraint checks
    if args.quantity < 1 or args.quantity > 50:
        print("Error: Quantity must be between 1 and 50.", file=sys.stderr)
        sys.exit(1)

    names = generate_names(
        args.category,
        args.style,
        args.quantity,
        args.alliterate,
        args.custom_data,
    )

    if args.format == "json":
        output_str = json.dumps(names, indent=2)
    else:
        output_str = format_names_markdown(
            names, args.category, args.style, args.alliterate
        )

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as file:
                file.write(output_str)
            print(f"Suggestions written successfully to {args.output}")
        except IOError as err:
            print(f"Error saving file: {err}", file=sys.stderr)
            sys.exit(1)
    else:
        print(output_str)


if __name__ == "__main__":
    main()

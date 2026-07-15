"""Gift Idea Generator.

Suggests personalized gift ideas based on budget, recipient age,
relationship, and interests, with scoring-based matches.
"""

# pylint: disable=duplicate-code
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Set

# Built-in Gift Database
GIFTS: List[Dict[str, Any]] = [
    # Tech / Gaming
    {
        "name": "Mechanical Keyboard",
        "price": 80.0,
        "ages": {"teen", "adult"},
        "interests": {"tech", "gaming"},
        "relationships": {"friend", "partner", "sibling"},
        "desc": "Tactile clicky keys for office work or PC gaming.",
    },
    {
        "name": "Smart Fitness Band",
        "price": 45.0,
        "ages": {"teen", "adult", "senior"},
        "interests": {"tech", "fitness"},
        "relationships": {"friend", "partner", "sibling", "parent"},
        "desc": "Track steps, sleep patterns, and daily heart rate.",
    },
    {
        "name": "Wireless Charging Pad",
        "price": 20.0,
        "ages": {"teen", "adult", "senior"},
        "interests": {"tech"},
        "relationships": {"friend", "colleague", "sibling", "parent"},
        "desc": "Convenient desk companion for fast charging smartphones.",
    },
    # Cooking / Foodie
    {
        "name": "Chef's Knife & Sharpener Set",
        "price": 60.0,
        "ages": {"adult", "senior"},
        "interests": {"cooking"},
        "relationships": {"partner", "parent", "sibling"},
        "desc": "High-carbon stainless steel knife for effortless food prep.",
    },
    {
        "name": "Gourmet Hot Sauce Sampler Pack",
        "price": 25.0,
        "ages": {"teen", "adult"},
        "interests": {"cooking", "foodie"},
        "relationships": {"friend", "colleague", "sibling", "partner"},
        "desc": "Selection of unique spicy flavors ranging from mild to extreme.",
    },
    # Reading / Creativity / Art
    {
        "name": "Kindle Paperwhite E-reader",
        "price": 140.0,
        "ages": {"teen", "adult", "senior"},
        "interests": {"reading", "tech"},
        "relationships": {"partner", "parent", "sibling"},
        "desc": "Glare-free screen that reads like real paper, even in sunlight.",
    },
    {
        "name": "Leather-bound Journal & Calligraphy Pen",
        "price": 30.0,
        "ages": {"teen", "adult", "senior"},
        "interests": {"art", "reading"},
        "relationships": {"friend", "partner", "parent", "sibling"},
        "desc": "Thick unlined vintage pages perfect for sketching or writing.",
    },
    {
        "name": "Watercolor Painting Starter Set",
        "price": 35.0,
        "ages": {"child", "teen", "adult"},
        "interests": {"art"},
        "relationships": {"friend", "sibling", "parent", "partner"},
        "desc": "Includes premium paint pans, water brushes, and sketching pads.",
    },
    # Fitness / Outdoors
    {
        "name": "Insulated Stainless Steel Water Bottle",
        "price": 25.0,
        "ages": {"child", "teen", "adult", "senior"},
        "interests": {"fitness", "outdoors"},
        "relationships": {"friend", "colleague", "sibling", "parent", "partner"},
        "desc": "Keeps beverages ice-cold for 24 hours or hot for 12 hours.",
    },
    {
        "name": "Resistance Bands & Exercise Guide Set",
        "price": 15.0,
        "ages": {"teen", "adult", "senior"},
        "interests": {"fitness"},
        "relationships": {"friend", "colleague", "sibling", "partner"},
        "desc": "Versatile home workouts setup ranging from light to heavy resistance.",
    },
    # Gardening
    {
        "name": "Herb Garden Windowsill Starter Kit",
        "price": 18.0,
        "ages": {"child", "teen", "adult", "senior"},
        "interests": {"gardening", "cooking"},
        "relationships": {"friend", "colleague", "parent", "sibling"},
        "desc": "Grow fresh basil, parsley, cilantro, and thyme right in your kitchen.",
    },
    # Children Toys / Games
    {
        "name": "Building Block Castle Set",
        "price": 40.0,
        "ages": {"child"},
        "interests": {"gaming", "art"},
        "relationships": {"sibling", "friend"},
        "desc": "Colorful interlocking blocks for creative castle construction.",
    },
    # General / Corporate
    {
        "name": "Gourmet Coffee Blend Basket",
        "price": 35.0,
        "ages": {"adult", "senior"},
        "interests": {"general", "cooking"},
        "relationships": {"colleague", "parent", "friend"},
        "desc": "Selection of three organic medium/dark roasts with a ceramic mug.",
    },
]


def load_gifts_database(custom_path: Optional[str]) -> List[Dict[str, Any]]:
    """Loads gift ideas from custom database or returns the built-in database.

    Args:
        custom_path: Optional path to custom JSON database.

    Returns:
        List of gift idea dictionaries.
    """
    if not custom_path:
        return GIFTS

    if not os.path.exists(custom_path):
        print(
            f"Warning: Custom data path '{custom_path}' does not exist. "
            "Using built-in database.",
            file=sys.stderr,
        )
        return GIFTS

    try:
        with open(custom_path, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, list):
                # Ensure structure matches set conversion for comparison
                for item in data:
                    item["ages"] = set(item.get("ages", []))
                    item["interests"] = set(item.get("interests", []))
                    item["relationships"] = set(item.get("relationships", []))
                return data
    except (json.JSONDecodeError, ValueError) as err:
        print(
            f"Warning: Failed to parse custom gifts database ({err}). "
            "Using built-in database.",
            file=sys.stderr,
        )
    return GIFTS


def score_gift(
    gift: Dict[str, Any],
    age: str,
    relationship: str,
    interests: Set[str],
) -> int:
    """Calculates compatibility score of a gift based on profile matches.

    Args:
        gift: Gift idea dictionary.
        age: Target recipient age group.
        relationship: Relationship type.
        interests: Set of recipient interests.

    Returns:
        Aggregated integer score.
    """
    score = 0
    # Interest matches (primary weighting)
    gift_interests = gift["interests"]
    matched_interests = interests.intersection(gift_interests)
    score += len(matched_interests) * 3

    # If 'general' interest matches when no other matches
    if not matched_interests and "general" in gift_interests:
        score += 1

    # Age match
    if age.lower() in gift["ages"]:
        score += 2

    # Relationship match
    if relationship.lower() in gift["relationships"]:
        score += 1

    return score


def generate_gift_ideas(
    age: str,
    max_budget: float,
    interests_str: str,
    relationship: str,
    num_gifts: int = 5,
    custom_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Generates and ranks gift recommendations based on scoring criteria.

    Args:
        age: Recipient age group.
        max_budget: Upper pricing boundary.
        interests_str: Comma-separated interests.
        relationship: Recipient relation status.
        num_gifts: Maximum results returning size.
        custom_path: Optional custom JSON file path.

    Returns:
        Sorted list of matched recommendations.
    """
    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    gift_db = load_gifts_database(custom_path)

    # Parse inputs
    interests = {i.strip().lower() for i in interests_str.split(",") if i.strip()}

    # Filter by budget
    affordable = [g for g in gift_db if g["price"] <= max_budget]

    scored_items = []
    for gift in affordable:
        score = score_gift(gift, age, relationship, interests)
        if score > 0:
            scored_items.append((score, gift))

    # Sort descending by score, then ascending by price
    scored_items.sort(key=lambda x: (-x[0], x[1]["price"]))

    results = []
    for score, item in scored_items[:num_gifts]:
        item_copy = item.copy()
        item_copy["match_score"] = score
        # Convert sets back to list for JSON serialization compatibility
        item_copy["ages"] = list(item_copy["ages"])
        item_copy["interests"] = list(item_copy["interests"])
        item_copy["relationships"] = list(item_copy["relationships"])
        results.append(item_copy)

    # General fallback if nothing matched
    if not results:
        fallback_gift = {
            "name": "Custom Gift Card (Bookstore/Coffee)",
            "price": max_budget,
            "desc": (
                f"A versatile gift card tailored for a {relationship} to explore "
                f"their favorite things."
            ),
            "match_score": 1,
            "ages": [age],
            "interests": ["general"],
            "relationships": [relationship],
        }
        results.append(fallback_gift)

    return results


def format_gift_ideas_markdown(
    ideas: List[Dict[str, Any]],
    age: str,
    budget: float,
    interests: str,
    relationship: str,
) -> str:
    """Formats list of gift recommendations as a Markdown document.

    Args:
        ideas: List of recommendation dicts.
        age: Recipient age tier.
        budget: Maximum cost filter.
        interests: Comma-separated interests.
        relationship: Relation category.

    Returns:
        Markdown-formatted string.
    """
    md = []
    md.append("# Gift Recommendations Guide")
    md.append("")
    md.append(
        f"**Recipient Profile**: {age.title()} | "
        f"**Relationship**: {relationship.title()} | "
        f"**Max Budget**: ${budget:.2f}"
    )
    md.append(f"**Interests**: {interests}")
    md.append("")
    md.append("---")
    md.append("")

    for i, gift in enumerate(ideas):
        md.append(f"### {i+1}. {gift['name']}")
        md.append(f"- **Estimated Price**: ${gift['price']:.2f}")
        md.append(f"- **Recommendation Score**: {gift['match_score']}")
        md.append(f"- **Description**: {gift['desc']}")
        md.append("")

    return "\n".join(md)


def main() -> None:
    """CLI entry point for gift-idea-generator."""
    parser = argparse.ArgumentParser(
        description="Generate personalized gift ideas based on recipient profiles."
    )
    parser.add_argument(
        "-a",
        "--age",
        choices=["child", "teen", "adult", "senior"],
        default="adult",
        help="Recipient age group (default: adult).",
    )
    parser.add_argument(
        "-b",
        "--budget",
        type=float,
        default=50.0,
        help="Max budget limit in dollars (default: 50.0).",
    )
    parser.add_argument(
        "-i",
        "--interests",
        default="general",
        help="Comma-separated interests (e.g. gaming, reading, cooking, fitness).",
    )
    parser.add_argument(
        "-r",
        "--relationship",
        choices=["friend", "partner", "parent", "sibling", "colleague"],
        default="friend",
        help="Relationship category (default: friend).",
    )
    parser.add_argument(
        "-n",
        "--num-gifts",
        type=int,
        default=5,
        help="Number of recommendations to suggest (default: 5).",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output serialization format (default: markdown).",
    )
    parser.add_argument("-o", "--output", help="Write list to file instead of stdout.")
    parser.add_argument(
        "--custom-data",
        help="Path to custom JSON file containing gift definitions.",
    )

    args = parser.parse_args()

    # Constraint checks
    if args.budget <= 0:
        print("Error: Budget must be greater than zero.", file=sys.stderr)
        sys.exit(1)
    if args.num_gifts < 1:
        print("Error: Number of gifts must be at least 1.", file=sys.stderr)
        sys.exit(1)

    recommendations = generate_gift_ideas(
        args.age,
        args.budget,
        args.interests,
        args.relationship,
        args.num_gifts,
        args.custom_data,
    )

    if args.format == "json":
        output_str = json.dumps(recommendations, indent=2)
    else:
        output_str = format_gift_ideas_markdown(
            recommendations,
            args.age,
            args.budget,
            args.interests,
            args.relationship,
        )

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as file:
                file.write(output_str)
            print(f"Gift recommendations written successfully to {args.output}")
        except IOError as err:
            print(f"Error saving file: {err}", file=sys.stderr)
            sys.exit(1)
    else:
        print(output_str)


if __name__ == "__main__":
    main()

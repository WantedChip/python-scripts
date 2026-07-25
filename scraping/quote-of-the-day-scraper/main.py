"""Quote of the Day Scraper CLI.

Fetches daily inspirational quotes from public APIs, deduplicates them against
an existing Markdown collection file, and appends formatted Markdown quote
blocks.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import datetime
import json
import os
import random
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Optional

FALLBACK_QUOTES = [
    {
        "quote": "The best way to predict the future is to create it.",
        "author": "Peter Drucker",
    },
    {
        "quote": "Code is like humor. When you have to explain it, it's bad.",
        "author": "Cory House",
    },
    {
        "quote": "Simplicity is prerequisite for reliability.",
        "author": "Edsger W. Dijkstra",
    },
]


def fetch_quote_from_api(source: str = "zenquotes") -> Dict[str, str]:
    """Fetch quote of the day from public API.

    Args:
        source: API provider ('zenquotes', 'dummyjson', 'quotable').

    Returns:
        Dictionary with keys 'quote' and 'author'.
    """
    url_map = {
        "zenquotes": "https://zenquotes.io/api/today",
        "dummyjson": "https://dummyjson.com/quotes/random",
        "quotable": "https://api.quotable.io/random",
    }

    url = url_map.get(source, url_map["zenquotes"])

    try:
        headers = {"User-Agent": "QuoteOfTheDayScraper/1.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))

            if source == "zenquotes" and isinstance(data, list) and data:
                q_text = data[0].get("q", "").strip()
                a_text = data[0].get("a", "Unknown").strip()
                return {"quote": q_text, "author": a_text}
            if source == "dummyjson" and isinstance(data, dict):
                q_text = data.get("quote", "").strip()
                a_text = data.get("author", "Unknown").strip()
                return {"quote": q_text, "author": a_text}
            if source == "quotable" and isinstance(data, dict):
                q_text = data.get("content", "").strip()
                a_text = data.get("author", "Unknown").strip()
                return {"quote": q_text, "author": a_text}
    except (
        urllib.error.URLError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ):
        pass

    # Fallback if network or API fails
    return random.choice(FALLBACK_QUOTES)  # nosec B311


def is_quote_duplicate(existing_markdown: str, quote_text: str) -> bool:
    """Check if quote text already exists in collection.

    Args:
        existing_markdown: Raw content of existing markdown file.
        quote_text: Quote text to search.

    Returns:
        True if quote is found in existing content, False otherwise.
    """
    clean_quote = quote_text.strip().lower()
    return clean_quote in existing_markdown.lower()


def format_quote_markdown(
    quote_text: str, author: str, category: Optional[str] = None
) -> str:
    """Format quote and author into a Markdown block string.

    Args:
        quote_text: Quote string.
        author: Author string.
        category: Optional category string.

    Returns:
        Formatted Markdown block string.
    """
    today_str = datetime.date.today().isoformat()
    cat_suffix = f" | *Category: {category}*" if category else ""
    lines = [
        f'> "{quote_text}"',
        f"> — **{author}**",
        f"*Added: {today_str}*{cat_suffix}",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def append_quote_to_file(
    filepath: str,
    quote_text: str,
    author: str,
    category: Optional[str] = None,
    force: bool = False,
) -> bool:
    """Append formatted quote block to markdown file if not duplicate.

    Args:
        filepath: Destination Markdown file path.
        quote_text: Quote text.
        author: Author name.
        category: Optional category label.
        force: If True, bypass deduplication.

    Returns:
        True if quote was appended, False if duplicate skipped.
    """
    existing_content = ""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing_content = f.read()

    if not force and is_quote_duplicate(existing_content, quote_text):
        return False

    md_block = format_quote_markdown(quote_text, author, category=category)

    # Initialize file header if file is empty
    prefix = ""
    if not existing_content.strip():
        prefix = "# Personal Quote Collection\n\n"

    with open(filepath, "a", encoding="utf-8") as f:
        f.write(prefix + md_block)

    return True


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Fetch daily quote and append to Markdown collection."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-o",
        "--output",
        default="quotes.md",
        help="Path to markdown collection file",
    )
    parser.add_argument(
        "-c",
        "--category",
        help="Optional category tag (e.g. Motivation, Tech)",
    )
    parser.add_argument(
        "-s",
        "--source",
        choices=["zenquotes", "dummyjson", "quotable"],
        default="zenquotes",
        help="Quote API provider",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force append even if quote is duplicate",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for quote of the day scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    print(f"Fetching quote from '{parsed.source}'...")
    quote_data = fetch_quote_from_api(source=parsed.source)
    quote_text = quote_data["quote"]
    author = quote_data["author"]

    print(f'\nQuote: "{quote_text}"')
    print(f"Author: {author}\n")

    appended = append_quote_to_file(
        parsed.output,
        quote_text,
        author,
        category=parsed.category,
        force=parsed.force,
    )

    if appended:
        print(f"Successfully appended quote to {parsed.output}")
    else:
        msg = f"Quote already exists in {parsed.output}. Skipped entry."
        print(msg)

    return 0


if __name__ == "__main__":
    sys.exit(main())

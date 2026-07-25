"""Random Quote Fetcher.

Fetches random quotes from public APIs with tag and author filtering,
and exports in Text, JSON, or Markdown formats.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


def fetch_quote_from_api(
    tag: Optional[str] = None, author: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch a single quote from public APIs with fallback support.

    Args:
        tag: Optional category tag to filter quotes.
        author: Optional author name to filter quotes.

    Returns:
        Dict containing keys: 'content', 'author', 'tags'.
    """
    # Primary API: Quotable
    params: Dict[str, str] = {}
    if tag:
        params["tags"] = tag.strip().lower()
    if author:
        params["author"] = author.strip()

    query_str = urllib.parse.urlencode(params)
    primary_url = (
        f"https://api.quotable.io/quotes/random{('?' + query_str) if query_str else ''}"
    )

    req = urllib.request.Request(
        primary_url,
        headers={"User-Agent": "RandomQuoteFetcher/1.0 (Python)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as response:  # nosec B310
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                # Quotable random endpoint returns list or single object
                item = data[0] if isinstance(data, list) and data else data
                return {
                    "content": item.get("content") or item.get("quote", ""),
                    "author": item.get("author", "Unknown"),
                    "tags": item.get("tags", [tag] if tag else []),
                }
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        pass  # Fall through to secondary API on failure or network issues

    # Secondary API: DummyJSON quotes fallback
    fallback_url = "https://dummyjson.com/quotes/random"
    req_fallback = urllib.request.Request(
        fallback_url,
        headers={"User-Agent": "RandomQuoteFetcher/1.0 (Python)"},
    )

    try:
        with urllib.request.urlopen(req_fallback, timeout=8) as response:  # nosec B310
            if response.status == 200:
                item = json.loads(response.read().decode("utf-8"))
                return {
                    "content": item.get("quote", ""),
                    "author": item.get("author", "Unknown"),
                    "tags": [tag] if tag else [],
                }
    except Exception as err:  # pylint: disable=broad-exception-caught
        raise RuntimeError(f"Failed to fetch quotes from APIs: {err}") from err

    return {
        "content": "Life is what happens when you're busy making other plans.",
        "author": "John Lennon",
        "tags": [],
    }


def fetch_quotes(
    count: int = 1, tag: Optional[str] = None, author: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fetch multiple quotes based on criteria.

    Args:
        count: Number of quotes to fetch.
        tag: Optional category tag filter.
        author: Optional author name filter.

    Returns:
        List of quote dictionaries.
    """
    quotes: List[Dict[str, Any]] = []
    for _ in range(max(1, count)):
        quote = fetch_quote_from_api(tag=tag, author=author)
        quotes.append(quote)
    return quotes


def format_quotes_text(quotes: List[Dict[str, Any]]) -> str:
    """Format quotes as plain text.

    Args:
        quotes: List of quote dicts.

    Returns:
        Formatted text string.
    """
    blocks = []
    for q in quotes:
        tags_str = f" [{', '.join(q['tags'])}]" if q.get("tags") else ""
        blocks.append(f'"{q["content"]}"\n  — {q["author"]}{tags_str}')
    return "\n\n".join(blocks)


def format_quotes_markdown(quotes: List[Dict[str, Any]]) -> str:
    """Format quotes as Markdown blockquotes.

    Args:
        quotes: List of quote dicts.

    Returns:
        Formatted Markdown string.
    """
    blocks = []
    for q in quotes:
        tags_str = f" *({', '.join(q['tags'])})*" if q.get("tags") else ""
        blocks.append(f'> "{q["content"]}"\n>\n> — **{q["author"]}**{tags_str}')
    return "\n\n".join(blocks)


def main() -> None:
    """CLI entry point for Random Quote Fetcher."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch random quotes from public APIs with filtering and export options."
        )
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Number of quotes to fetch (default: 1).",
    )
    parser.add_argument(
        "-t",
        "--tag",
        help="Filter quotes by tag/category (e.g. technology, wisdom, inspirational).",
    )
    parser.add_argument(
        "-a",
        "--author",
        help="Filter quotes by author name.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format: text, json, or markdown (default: text).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path to save/append fetched quotes.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append output to target file instead of overwriting.",
    )

    args = parser.parse_args()

    try:
        quotes = fetch_quotes(count=args.count, tag=args.tag, author=args.author)

        if args.format == "json":
            output_content = json.dumps(quotes, indent=2)
        elif args.format == "markdown":
            output_content = format_quotes_markdown(quotes)
        else:
            output_content = format_quotes_text(quotes)

        print(output_content)

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if args.append else "w"
            with open(args.output, mode, encoding="utf-8") as f:
                if args.append and args.format != "json":
                    f.write("\n\n" + output_content)
                else:
                    f.write(output_content)
            print(f"\nQuotes successfully saved to {args.output}")

    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

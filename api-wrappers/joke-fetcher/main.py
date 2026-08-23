"""Joke Fetcher.

Retrieves programming or general jokes from JokeAPI (v2) and displays them cleanly.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, cast

VALID_CATEGORIES = ["Any", "Programming", "Misc", "Pun", "Spooky", "Christmas", "Dark"]


def fetch_joke(
    category: str = "Programming", safe_mode: bool = True
) -> Optional[Dict[str, Any]]:
    """Fetch joke from JokeAPI v2.

    Args:
        category: Joke category (e.g. 'Programming', 'Misc', 'Pun').
        safe_mode: If True, appends safe-mode query parameter.

    Returns:
        JSON response payload as dict, or None on failure.
    """
    cat = category.strip() or "Programming"
    params = []
    if safe_mode:
        params.append("safe-mode")

    query_str = f"?{'&'.join(params)}" if params else ""
    url = f"https://v2.jokeapi.dev/joke/{urllib.parse.quote(cat)}{query_str}"

    req = urllib.request.Request(url, headers={"User-Agent": "JokeFetcher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
            if response.status == 200:
                data = response.read().decode("utf-8")
                return cast(Dict[str, Any], json.loads(data))
    except urllib.error.HTTPError as err:
        print(f"HTTP Error {err.code}: {err.reason}", file=sys.stderr)
    except urllib.error.URLError as err:
        print(f"Network Error: {err.reason}", file=sys.stderr)
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error fetching joke: {err}", file=sys.stderr)

    return None


def parse_joke(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse JokeAPI payload into a normalized structure.

    Args:
        raw_data: Dictionary returned by JokeAPI.

    Returns:
        Normalized dictionary with fields: error, type, category, setup, delivery, joke.
    """
    if raw_data.get("error"):
        return {
            "error": True,
            "message": raw_data.get("message", "Unknown API error"),
        }

    joke_type = raw_data.get("type", "single")
    category = raw_data.get("category", "General")

    if joke_type == "twopart":
        return {
            "error": False,
            "type": "twopart",
            "category": category,
            "setup": raw_data.get("setup", ""),
            "delivery": raw_data.get("delivery", ""),
            "joke": f"{raw_data.get('setup')}\n{raw_data.get('delivery')}",
        }

    return {
        "error": False,
        "type": "single",
        "category": category,
        "setup": None,
        "delivery": None,
        "joke": raw_data.get("joke", ""),
    }


def format_joke_output(parsed_joke: Dict[str, Any]) -> str:
    """Format parsed joke dictionary for terminal display.

    Args:
        parsed_joke: Normalized joke dict.

    Returns:
        Formatted string output.
    """
    if parsed_joke.get("error"):
        return f"[ERROR] {parsed_joke.get('message')}"

    lines = []
    lines.append("=" * 60)
    lines.append(f"  JOKE ({parsed_joke['category']} - {parsed_joke['type'].upper()})")
    lines.append("=" * 60)

    if parsed_joke["type"] == "twopart":
        lines.append(f"Q: {parsed_joke['setup']}")
        lines.append(f"A: {parsed_joke['delivery']}")
    else:
        lines.append(parsed_joke["joke"])

    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> None:
    """CLI entry point for Joke Fetcher."""
    parser = argparse.ArgumentParser(description="Fetch jokes from JokeAPI v2.")
    parser.add_argument(
        "-c",
        "--category",
        type=str,
        default="Programming",
        choices=VALID_CATEGORIES,
        help="Joke category (Programming, Misc, Pun, etc.)",
    )
    parser.add_argument(
        "--unsafe",
        action="store_true",
        help="Disable safe mode (allow dark/nsfw jokes if available)",
    )

    args = parser.parse_args()
    safe_mode = not args.unsafe

    raw_data = fetch_joke(category=args.category, safe_mode=safe_mode)
    if not raw_data:
        sys.exit(1)

    parsed = parse_joke(raw_data)
    print(format_joke_output(parsed))


if __name__ == "__main__":
    main()

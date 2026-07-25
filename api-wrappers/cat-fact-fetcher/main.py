#!/usr/bin/env python3
"""Cat Fact Fetcher script.

Fetches random cat facts from Cat Facts API (`catfact.ninja`) and accumulates
them into a local collection file with deduplication.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

CAT_FACT_API_URL = "https://catfact.ninja/fact"


def fetch_cat_fact(timeout: int = 10) -> Optional[str]:
    """Fetch a single random cat fact from Cat Facts API.

    Args:
        timeout: Request timeout in seconds.

    Returns:
        Cat fact string or None if API request fails.
    """
    req = urllib.request.Request(
        CAT_FACT_API_URL, headers={"User-Agent": "CatFactFetcher/1.0 (Python)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                payload = json.loads(response.read().decode("utf-8"))
                fact = payload.get("fact")
                return fact.strip() if fact else None
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error fetching cat fact: {err}", file=sys.stderr)
    return None


def load_existing_facts(filepath: str) -> List[str]:
    """Load existing cat facts from a local JSON or Markdown file.

    Args:
        filepath: Path to facts file.

    Returns:
        List of fact strings existing in the file.
    """
    path = Path(filepath)
    if not path.exists():
        return []

    ext = path.suffix.lower()
    try:
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        elif ext in (".md", ".markdown"):
            facts = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str.startswith("- ") or line_str.startswith("* "):
                        facts.append(line_str[2:].strip())
                    elif line_str and not line_str.startswith("#"):
                        match = re.match(r"^\d+\.\s+(.*)$", line_str)
                        if match:
                            facts.append(match.group(1).strip())
                        else:
                            facts.append(line_str)
            return facts
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(
            f"Warning: Could not parse existing file {filepath}: {err}", file=sys.stderr
        )

    return []


def save_facts_json(facts: List[str], filepath: str) -> bool:
    """Save list of facts to a JSON file.

    Args:
        facts: List of facts.
        filepath: Output path.

    Returns:
        True if success, False otherwise.
    """
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(facts, f, indent=2, ensure_ascii=False)
        return True
    except OSError as err:
        print(f"Error saving facts JSON to {filepath}: {err}", file=sys.stderr)
        return False


def save_facts_md(facts: List[str], filepath: str) -> bool:
    """Save list of facts to a Markdown file.

    Args:
        facts: List of facts.
        filepath: Output path.

    Returns:
        True if success, False otherwise.
    """
    try:
        lines = ["# Cat Facts Collection\n"]
        for idx, fact in enumerate(facts, 1):
            lines.append(f"{idx}. {fact}\n")
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except OSError as err:
        print(f"Error saving facts Markdown to {filepath}: {err}", file=sys.stderr)
        return False


def accumulate_facts(count: int, filepath: str) -> Tuple[List[str], int]:
    """Fetch `count` new unique facts and append them to local collection file.

    Args:
        count: Number of new facts to attempt fetching.
        filepath: Target collection file path (.json or .md).

    Returns:
        Tuple of (list of newly added facts, total count in collection).
    """
    existing_facts = load_existing_facts(filepath)
    fact_set = set(existing_facts)
    newly_added: List[str] = []

    attempts = 0
    max_attempts = count * 3

    while len(newly_added) < count and attempts < max_attempts:
        attempts += 1
        fact = fetch_cat_fact()
        if fact and fact not in fact_set:
            fact_set.add(fact)
            newly_added.append(fact)
            existing_facts.append(fact)

    ext = Path(filepath).suffix.lower()
    if ext in (".md", ".markdown"):
        save_facts_md(existing_facts, filepath)
    else:
        save_facts_json(existing_facts, filepath)

    return newly_added, len(existing_facts)


def main() -> None:
    """Main CLI entrypoint for Cat Fact Fetcher."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch random cat facts and accumulate them in a local collection file."
        )
    )
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=1,
        help="Number of new cat facts to fetch (default: 1)",
    )
    parser.add_argument(
        "--file",
        "-f",
        default="cat_facts.json",
        help="Path to local facts storage file (.json or .md)",
    )

    args = parser.parse_args()

    print(f"Fetching {args.count} new cat fact(s)...")
    added, total = accumulate_facts(args.count, args.file)

    if added:
        print("\nNew Cat Facts Added:")
        for idx, f in enumerate(added, 1):
            print(f"  [{idx}] {f}")
        print(
            f"\nSuccessfully updated '{args.file}'. Total facts in collection: {total}"
        )
    else:
        print("No new unique facts could be added at this time.", file=sys.stderr)


if __name__ == "__main__":
    main()

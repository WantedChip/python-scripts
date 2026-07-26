"""Dictionary Lookup CLI.

Command-line tool to query word definitions, pronunciations, synonyms,
and antonyms via REST API with an offline fallback lexicon.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

API_URL_TEMPLATE = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

OFFLINE_LEXICON: Dict[str, List[Dict[str, Any]]] = {
    "python": [
        {
            "word": "python",
            "phonetic": "/ˈpaɪθɑːn/",
            "meanings": [
                {
                    "partOfSpeech": "noun",
                    "definitions": [
                        {
                            "definition": (
                                "A large nonvenomous snake which kills by "
                                "constriction."
                            ),
                            "example": "The python wrapped around the branch.",
                        },
                        {
                            "definition": (
                                "A high-level interpreted programming language "
                                "designed for readability."
                            ),
                            "example": (
                                "We wrote a script in Python to automate the "
                                "data workflow."
                            ),
                        },
                    ],
                    "synonyms": ["snake", "serpent", "programming language"],
                    "antonyms": [],
                }
            ],
        }
    ],
    "algorithm": [
        {
            "word": "algorithm",
            "phonetic": "/ˈælɡəˌrɪðəm/",
            "meanings": [
                {
                    "partOfSpeech": "noun",
                    "definitions": [
                        {
                            "definition": (
                                "A process or set of rules to be followed in "
                                "calculations or problem-solving operations."
                            ),
                            "example": (
                                "Sorting algorithms arrange items in a "
                                "specific numerical order."
                            ),
                        }
                    ],
                    "synonyms": ["procedure", "formula", "routine", "protocol"],
                    "antonyms": [],
                }
            ],
        }
    ],
    "fast": [
        {
            "word": "fast",
            "phonetic": "/fæst/",
            "meanings": [
                {
                    "partOfSpeech": "adjective",
                    "definitions": [
                        {
                            "definition": (
                                "Moving or capable of moving at high speed."
                            ),
                            "example": "A fast car zoomed down the highway.",
                        }
                    ],
                    "synonyms": ["quick", "rapid", "swift", "speedy"],
                    "antonyms": ["slow", "sluggish", "tardy"],
                }
            ],
        }
    ],
    "code": [
        {
            "word": "code",
            "phonetic": "/koʊd/",
            "meanings": [
                {
                    "partOfSpeech": "noun",
                    "definitions": [
                        {
                            "definition": (
                                "A system of words, letters, figures, or "
                                "symbols used to represent others."
                            ),
                            "example": (
                                "The developer wrote Python code for the "
                                "application."
                            ),
                        }
                    ],
                    "synonyms": ["cipher", "script", "program", "encoding"],
                    "antonyms": [],
                }
            ],
        }
    ],
}


class DictionaryClient:
    """Client for fetching dictionary entries online or from offline fallback."""

    def __init__(self, offline_only: bool = False, timeout: int = 5) -> None:
        self.offline_only = offline_only
        self.timeout = timeout

    def fetch_online(self, word: str) -> Optional[List[Dict[str, Any]]]:
        """Fetches definition entry from public REST API."""
        url = API_URL_TEMPLATE.format(word=urllib.parse.quote(word.lower()))
        req = urllib.request.Request(
            url, headers={"User-Agent": "DictionaryLookupCLI/1.0"}
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as resp:  # nosec B310
                if resp.status == 200:
                    data = resp.read().decode("utf-8")
                    res = json.loads(data)
                    return res if isinstance(res, list) else None
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
            return None
        return None

    def fetch_offline(self, word: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieves definition from offline dictionary fallback."""
        w_lower = word.lower().strip()
        if w_lower in OFFLINE_LEXICON:
            return OFFLINE_LEXICON[w_lower]
        return None

    def lookup(self, word: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """Looks up word definitions.

        Returns (data, source) tuple.
        Source will be 'online' or 'offline'.
        """
        if not self.offline_only:
            online_res = self.fetch_online(word)
            if online_res:
                return online_res, "online"

        offline_res = self.fetch_offline(word)
        if offline_res:
            return offline_res, "offline"

        return None, "none"


def format_display(word: str, entries: List[Dict[str, Any]], source: str) -> None:
    """Formats and prints dictionary lookup results cleanly."""
    print("\n" + "=" * 60)
    print(f" WORD DEFINITION: {word.upper()} (Source: {source.upper()})")
    print("=" * 60)

    for entry in entries:
        phonetics = entry.get("phonetic", "")
        if not phonetics and entry.get("phonetics"):
            for p in entry["phonetics"]:
                if p.get("text"):
                    phonetics = p["text"]
                    break

        if phonetics:
            print(f"Pronunciation: {phonetics}")

        meanings = entry.get("meanings", [])
        for idx, meaning in enumerate(meanings, 1):
            pos = meaning.get("partOfSpeech", "general")
            print(f"\n[{idx}] Part of Speech: {pos.upper()}")

            defs = meaning.get("definitions", [])
            for d_idx, d_item in enumerate(defs, 1):
                defn = d_item.get("definition", "")
                ex = d_item.get("example", "")
                print(f"   {d_idx}. {defn}")
                if ex:
                    print(f'      Example: "{ex}"')

            syns = meaning.get("synonyms", [])
            ants = meaning.get("antonyms", [])

            if syns:
                print(f"   Synonyms: {', '.join(syns)}")
            if ants:
                print(f"   Antonyms: {', '.join(ants)}")

    print("-" * 60 + "\n")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Dictionary Lookup CLI")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    lookup_parser = subparsers.add_parser("lookup", help="Look up a word")
    lookup_parser.add_argument("word", help="Word to look up")
    lookup_parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Force offline lexicon lookup",
    )
    lookup_parser.add_argument(
        "--synonyms", action="store_true", help="Display synonyms only"
    )
    lookup_parser.add_argument(
        "--antonyms", action="store_true", help="Display antonyms only"
    )
    lookup_parser.add_argument(
        "--json", action="store_true", help="Output raw JSON response"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.command == "lookup":
        client = DictionaryClient(offline_only=parsed.offline_only)
        entries, source = client.lookup(parsed.word)

        if not entries:
            err_msg = (
                f"Error: Word '{parsed.word}' not found in online API "
                "or offline fallback lexicon."
            )
            print(err_msg)
            return 1

        if parsed.json:
            print(json.dumps({"source": source, "data": entries}, indent=2))
            return 0

        if parsed.synonyms or parsed.antonyms:
            all_syns = set()
            all_ants = set()
            for entry in entries:
                for meaning in entry.get("meanings", []):
                    all_syns.update(meaning.get("synonyms", []))
                    all_ants.update(meaning.get("antonyms", []))

            if parsed.synonyms:
                syn_str = ", ".join(sorted(all_syns)) if all_syns else "None found."
                print(f"\nSynonyms for '{parsed.word}': {syn_str}")
            if parsed.antonyms:
                ant_str = ", ".join(sorted(all_ants)) if all_ants else "None found."
                print(f"Antonyms for '{parsed.word}': {ant_str}")
            return 0

        format_display(parsed.word, entries, source)
    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())

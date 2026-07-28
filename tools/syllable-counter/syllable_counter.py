"""Count syllables in English words or text passages using linguistic heuristics.

This module provides syllable counting capabilities for single words and full
passages using heuristic rules (vowel groups, silent 'e', 'le' suffixes,
prefix/suffix patterns, diphthongs, and special cases).
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals

import argparse
import json
import logging
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Basic Vowels pattern
VOWELS = set("aeiouyAEIOUY")


def count_syllables_word(word: str) -> int:
    """Estimate the number of syllables in a single English word.

    Args:
        word: Cleaned English word string.

    Returns:
        Integer count of estimated syllables (minimum 1 for non-empty words).
    """
    cleaned = word.strip().lower()
    cleaned = re.sub(r"[^a-z]", "", cleaned)

    if not cleaned:
        return 0

    if len(cleaned) <= 3:
        return 1

    # Exception dictionary for common irregular words
    exceptions: Dict[str, int] = {
        "area": 3,
        "idea": 3,
        "real": 1,
        "really": 2,
        "family": 3,
        "every": 2,
        "different": 3,
        "favourite": 3,
        "favorite": 3,
        "business": 2,
        "chocolate": 3,
        "rhythm": 2,
        "smile": 1,
        "spaghetti": 3,
        "recipe": 3,
        "create": 2,
        "creator": 3,
        "poem": 2,
        "poet": 2,
        "poetry": 3,
        "science": 2,
        "quiet": 2,
        "lion": 2,
        "violet": 3,
        "theater": 3,
        "theatre": 3,
    }

    if cleaned in exceptions:
        return exceptions[cleaned]

    # Handle trailing silent 'e' or 'le'
    working = cleaned
    is_le_ending = False

    if working.endswith("le") and len(working) > 2 and working[-3] not in VOWELS:
        is_le_ending = True
        working = working[:-2]  # strip 'le', count +1 for it later
    elif working.endswith("e") and not working.endswith("ee") and len(working) > 2:
        working = working[:-1]

    # Count contiguous vowel groups in working stem
    count = 0
    in_vowel = False

    for char in working:
        if char in VOWELS:
            if not in_vowel:
                count += 1
                in_vowel = True
        else:
            in_vowel = False

    if is_le_ending:
        count += 1

    if cleaned.endswith("ed") and len(cleaned) > 3:
        if not (cleaned.endswith("ted") or cleaned.endswith("ded")):
            if count > 1:
                count -= 1

    if cleaned.endswith("es") and len(cleaned) > 3:
        if not (
            cleaned.endswith("ches")
            or cleaned.endswith("shes")
            or cleaned.endswith("ses")
            or cleaned.endswith("zes")
            or cleaned.endswith("xes")
        ):
            if count > 1:
                count -= 1

    return max(1, count)


def analyze_text(text: str) -> Tuple[List[Tuple[str, int]], Dict[str, Any]]:
    """Analyze full text passage and compute syllable statistics.

    Args:
        text: Input text passage string.

    Returns:
        Tuple of (word_syllable_pairs, summary_stats_dict).
    """
    raw_tokens = re.findall(r"\b[a-zA-Z']+\b", text)
    word_counts: List[Tuple[str, int]] = []
    total_syllables = 0

    for token in raw_tokens:
        syllables = count_syllables_word(token)
        word_counts.append((token, syllables))
        total_syllables += syllables

    word_qty = len(raw_tokens)
    sentences = max(1, len(re.split(r"[.!?]+", text.strip())) - 1)
    if sentences == 0:
        sentences = 1

    avg_syllables = round(total_syllables / word_qty, 2) if word_qty > 0 else 0.0
    avg_words_per_sentence = round(word_qty / sentences, 2)

    readability = 0.0
    if word_qty > 0 and sentences > 0:
        readability = round(
            206.835
            - (1.015 * (word_qty / sentences))
            - (84.6 * (total_syllables / word_qty)),
            2,
        )

    summary: Dict[str, Any] = {
        "total_words": word_qty,
        "total_syllables": total_syllables,
        "total_sentences": sentences,
        "avg_syllables_per_word": avg_syllables,
        "avg_words_per_sentence": avg_words_per_sentence,
        "flesch_reading_ease": readability,
    }

    return word_counts, summary


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Count syllables in English words or text passages."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=str,
        help="Text string or input file path. Reads from stdin if omitted.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "summary"],
        default="text",
        help="Output display format (default: text).",
    )
    parser.add_argument(
        "-w",
        "--word",
        type=str,
        help="Count syllables for a single word only.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging output.",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI execution entrypoint.

    Args:
        args: Command-line arguments list or None for sys.argv[1:].

    Returns:
        Exit code integer (0 for success, non-zero for error).
    """
    parser = setup_cli_parser()
    parsed_args = parser.parse_args(args)

    log_level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if parsed_args.word is not None:
        cnt = count_syllables_word(parsed_args.word)
        if parsed_args.format == "json":
            print(json.dumps({"word": parsed_args.word, "syllables": cnt}, indent=2))
        else:
            print(f"Word: '{parsed_args.word}' -> {cnt} syllable(s)")
        return 0

    content = ""
    if parsed_args.input:
        try:
            with open(parsed_args.input, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            content = parsed_args.input
    else:
        try:
            if not sys.stdin.isatty():
                content = sys.stdin.read()
        except (OSError, ValueError):
            content = ""

    if not content.strip():
        logger.error("No input text provided or input is empty.")
        return 1

    word_counts, summary = analyze_text(content)

    if parsed_args.format == "json":
        output_data = {
            "summary": summary,
            "word_breakdown": [{"word": w, "syllables": s} for w, s in word_counts],
        }
        print(json.dumps(output_data, indent=2))
    elif parsed_args.format == "summary":
        print("=== Syllable & Readability Summary ===")
        for key, val in summary.items():
            formatted_key = key.replace("_", " ").title()
            print(f"{formatted_key}: {val}")
    else:
        print("=== Word Syllable Breakdown ===")
        for w, s in word_counts:
            print(f"{w:<20} {s} syllable(s)")
        print("\n=== Summary Stats ===")
        print(f"Total Words:             {summary['total_words']}")
        print(f"Total Syllables:         {summary['total_syllables']}")
        print(f"Avg Syllables / Word:    {summary['avg_syllables_per_word']}")
        print(f"Flesch Reading Ease:     {summary['flesch_reading_ease']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

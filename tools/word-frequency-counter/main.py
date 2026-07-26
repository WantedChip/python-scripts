"""Word Frequency Counter.

Tokenizes text files, filters stop words, and outputs sorted word frequency
rankings in console table, JSON, or CSV format.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Set, Tuple

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=broad-exception-caught


DEFAULT_STOP_WORDS: Set[str] = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "can't",
    "cannot",
    "could",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "he'd",
    "he'll",
    "he's",
    "her",
    "here",
    "here's",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "how's",
    "i",
    "i'd",
    "i'll",
    "i'm",
    "i've",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "let's",
    "me",
    "more",
    "most",
    "mustn't",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "she'd",
    "she'll",
    "she's",
    "should",
    "shouldn't",
    "so",
    "some",
    "such",
    "than",
    "that",
    "that's",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "there's",
    "these",
    "they",
    "they'd",
    "they'll",
    "they're",
    "they've",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "we'd",
    "we'll",
    "we're",
    "we've",
    "were",
    "weren't",
    "what",
    "what's",
    "when",
    "when's",
    "where",
    "where's",
    "which",
    "while",
    "who",
    "who's",
    "whom",
    "why",
    "why's",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "you'd",
    "you'll",
    "you're",
    "you've",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


def load_stop_words(custom_file: Optional[Path] = None) -> Set[str]:
    """Loads default stop words combined with optional custom stop words."""
    stop_words = set(DEFAULT_STOP_WORDS)
    if custom_file and custom_file.exists():
        content = custom_file.read_text(encoding="utf-8")
        custom_words = {w.strip().lower() for w in content.splitlines() if w.strip()}
        stop_words.update(custom_words)
    return stop_words


def tokenize(text: str, lower: bool = True) -> List[str]:
    """Tokenizes text into words using regex pattern."""
    if lower:
        text = text.lower()
    words = re.findall(r"\b[a-zA-Z0-9]+(?:'[a-zA-Z0-9]+)?\b", text)
    return words


def filter_and_count(
    words: List[str],
    stop_words: Set[str],
    min_length: int = 1,
    ignore_stop_words: bool = True,
) -> Counter[str]:
    """Filters words based on length and stop words, returning Counter."""
    filtered: List[str] = []
    for word in words:
        if len(word) < min_length:
            continue
        if ignore_stop_words and word.lower() in stop_words:
            continue
        filtered.append(word)
    return Counter(filtered)


def format_table(counts: List[Tuple[str, int]], total_words: int) -> str:
    """Formats top word counts into a formatted console table string."""
    lines: List[str] = []
    lines.append("=" * 50)
    lines.append(f"{'Rank':<6} {'Word':<24} {'Count':<8} {'Percentage':<10}")
    lines.append("-" * 50)

    for rank, (word, count) in enumerate(counts, start=1):
        percentage = (count / total_words * 100) if total_words > 0 else 0.0
        lines.append(f"{rank:<6} {word:<24} {count:<8} {percentage:.2f}%")

    lines.append("=" * 50)
    lines.append(f"Total Unique Filtered Words: {len(counts)}")
    lines.append(f"Total Token Count:           {total_words}")
    return "\n".join(lines)


def format_json(counts: List[Tuple[str, int]], total_words: int) -> str:
    """Formats word frequencies into a JSON string."""
    rankings = []
    for rank, (word, count) in enumerate(counts, start=1):
        pct = (count / total_words * 100) if total_words > 0 else 0.0
        rankings.append(
            {
                "rank": rank,
                "word": word,
                "count": count,
                "percentage": round(pct, 2),
            }
        )

    data = {
        "total_tokens": total_words,
        "unique_words": len(counts),
        "rankings": rankings,
    }
    return json.dumps(data, indent=2)


def format_csv(counts: List[Tuple[str, int]]) -> str:
    """Formats word frequencies into a CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Rank", "Word", "Count"])
    for rank, (word, count) in enumerate(counts, start=1):
        writer.writerow([rank, word, count])
    return output.getvalue()


def build_parser() -> argparse.ArgumentParser:
    """Builds CLI parser."""
    parser = argparse.ArgumentParser(description="Word Frequency Counter")
    parser.add_argument("input_file", type=str, help="Path to input text file")
    parser.add_argument(
        "--top",
        "-n",
        type=int,
        default=20,
        help="Number of top words to rank (default: 20)",
    )
    parser.add_argument(
        "--min-length",
        "-m",
        type=int,
        default=1,
        help="Minimum word length to include (default: 1)",
    )
    parser.add_argument(
        "--stop-words",
        type=str,
        default=None,
        help="Path to custom stop words text file",
    )
    parser.add_argument(
        "--include-stop-words",
        action="store_true",
        help="Do not filter out stop words",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    return parser


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command line arguments."""
    parser = build_parser()
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parsed = parse_args(args)
    input_path = Path(parsed.input_file)

    if not input_path.exists():
        print(f"Error: File not found '{input_path}'", file=sys.stderr)
        return 1

    try:
        text = input_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading file '{input_path}': {e}", file=sys.stderr)
        return 1

    custom_stop_path = Path(parsed.stop_words) if parsed.stop_words else None
    stop_words = load_stop_words(custom_stop_path)

    tokens = tokenize(text, lower=True)
    counts_counter = filter_and_count(
        tokens,
        stop_words=stop_words,
        min_length=parsed.min_length,
        ignore_stop_words=not parsed.include_stop_words,
    )

    top_counts = counts_counter.most_common(parsed.top)
    total_tokens = sum(counts_counter.values())

    if parsed.format == "json":
        print(format_json(top_counts, total_tokens))
    elif parsed.format == "csv":
        print(format_csv(top_counts), end="")
    else:
        print(format_table(top_counts, total_tokens))

    return 0


if __name__ == "__main__":
    sys.exit(main())

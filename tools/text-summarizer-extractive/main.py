"""Extractive Text Summarizer.

Generates extractive summaries by scoring and selecting the most important
sentences in a text document based on word frequency scoring.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=dangerous-default-value


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
    "could",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "me",
    "more",
    "most",
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
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
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
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "would",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


def split_sentences(text: str) -> List[str]:
    """Split text into sentences preserving meaningful punctuation boundary."""
    raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    return sentences


def calculate_word_frequencies(
    text: str, stop_words: Set[str] = DEFAULT_STOP_WORDS
) -> Dict[str, float]:
    """Calculate normalized word frequencies for non-stop words.

    Args:
        text: Input text content.
        stop_words: Set of words to ignore.

    Returns:
        Dictionary mapping word to normalized frequency (0.0 to 1.0).
    """
    words = re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())
    filtered_words = [w for w in words if w not in stop_words]

    if not filtered_words:
        return {}

    counts = Counter(filtered_words)
    max_freq = max(counts.values())

    return {word: count / max_freq for word, count in counts.items()}


def score_sentences(sentences: List[str], word_freqs: Dict[str, float]) -> List[float]:
    """Score each sentence based on normalized word frequencies.

    Args:
        sentences: List of sentence strings.
        word_freqs: Normalized word frequencies dictionary.

    Returns:
        List of numerical scores matching sentences by index.
    """
    scores: List[float] = []
    for sentence in sentences:
        words = re.findall(r"\b[a-zA-Z]{2,}\b", sentence.lower())
        if not words:
            scores.append(0.0)
            continue

        score = sum(word_freqs.get(word, 0.0) for word in words)
        # Length normalization to prevent bias towards long sentences
        normalized_score = score / math.sqrt(len(words))
        scores.append(round(normalized_score, 4))

    return scores


def summarize(
    text: str,
    ratio: float = 0.3,
    num_sentences: Optional[int] = None,
    stop_words: Set[str] = DEFAULT_STOP_WORDS,
) -> str:
    """Generate extractive text summary.

    Args:
        text: Target text to summarize.
        ratio: Target summary length ratio (0.0 < ratio <= 1.0).
        num_sentences: Specific sentence count (overrides ratio if provided).
        stop_words: Set of stop words.

    Returns:
        Extracted summary text string.
    """
    sentences = split_sentences(text)
    total = len(sentences)

    if total == 0:
        return ""
    if total <= 2:
        return text.strip()

    if num_sentences is not None and num_sentences > 0:
        target_count = min(num_sentences, total)
    else:
        target_count = max(1, math.ceil(total * ratio))

    word_freqs = calculate_word_frequencies(text, stop_words=stop_words)
    scores = score_sentences(sentences, word_freqs)

    # Pair indices with scores
    indexed_scores = list(enumerate(scores))
    # Sort by score descending
    sorted_by_score = sorted(indexed_scores, key=lambda x: x[1], reverse=True)
    # Pick top target_count sentence indices
    top_indices = sorted([item[0] for item in sorted_by_score[:target_count]])

    selected_sentences = [sentences[idx] for idx in top_indices]
    return " ".join(selected_sentences)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Generates extractive summary of text file using sentence"
        " importance scoring."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("file", type=Path, help="Path to text file")
    parser.add_argument(
        "--ratio",
        type=float,
        default=0.3,
        help="Summary ratio relative to total sentences (default: 0.3)",
    )
    parser.add_argument(
        "--sentences",
        type=int,
        default=None,
        help="Target sentence count (overrides --ratio)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file path to save summary",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Extractive Text Summarizer."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.file.exists():
        sys.stderr.write(f"Error: File '{parsed.file}' not found.\n")
        return 1

    content = parsed.file.read_text(encoding="utf-8")
    summary_text = summarize(
        content, ratio=parsed.ratio, num_sentences=parsed.sentences
    )

    if parsed.output:
        parsed.output.write_text(summary_text, encoding="utf-8")
        print(f"Summary written to {parsed.output}")
    else:
        print("\n--- Summary ---")
        print(summary_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())

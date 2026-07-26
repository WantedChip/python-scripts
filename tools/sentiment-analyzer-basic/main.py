"""Basic Sentiment Analyzer.

Performs rule-based sentiment scoring (positive, negative, neutral) on text
using a lexicon wordlist and basic negation handling.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_POSITIVE_WORDS: Set[str] = {
    "good",
    "great",
    "excellent",
    "amazing",
    "wonderful",
    "fantastic",
    "terrific",
    "outstanding",
    "superb",
    "awesome",
    "brilliant",
    "love",
    "like",
    "best",
    "happy",
    "pleased",
    "delighted",
    "positive",
    "perfect",
    "nice",
    "enjoy",
    "helpful",
    "clean",
    "fast",
    "efficient",
    "recommend",
    "impressive",
    "satisfied",
    "valuable",
    "friendly",
}

DEFAULT_NEGATIVE_WORDS: Set[str] = {
    "bad",
    "terrible",
    "awful",
    "horrible",
    "poor",
    "disappointing",
    "useless",
    "broken",
    "worst",
    "hate",
    "dislike",
    "sad",
    "angry",
    "upset",
    "negative",
    "flawed",
    "slow",
    "annoying",
    "frustrating",
    "waste",
    "unhelpful",
    "defective",
    "dirty",
    "problem",
    "fail",
    "failure",
    "expensive",
    "painful",
    "difficult",
    "buggy",
}

DEFAULT_NEGATORS: Set[str] = {
    "not",
    "no",
    "never",
    "none",
    "neither",
    "nor",
    "cannot",
    "cant",
    "can't",
    "don't",
    "dont",
    "doesn't",
    "doesnt",
    "won't",
    "wont",
    "isnt",
    "isn't",
}


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase words while preserving contraction punctuation.

    Args:
        text: Input text string.

    Returns:
        List of lowercase word tokens.
    """
    return re.findall(r"\b[\w']+\b", text.lower())


def analyze_sentiment(
    text: str,
    positive_words: Optional[Set[str]] = None,
    negative_words: Optional[Set[str]] = None,
    negators: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Analyze the sentiment of a text string.

    Args:
        text: Target text string.
        positive_words: Optional custom set of positive words.
        negative_words: Optional custom set of negative words.
        negators: Optional custom set of negator words.

    Returns:
        Dict containing score breakdown, classification, and matched words.
    """
    pos_set = positive_words if positive_words is not None else DEFAULT_POSITIVE_WORDS
    neg_set = negative_words if negative_words is not None else DEFAULT_NEGATIVE_WORDS
    negator_set = negators if negators is not None else DEFAULT_NEGATORS

    tokens = tokenize(text)
    total_tokens = len(tokens)

    matched_positive: List[str] = []
    matched_negative: List[str] = []

    i = 0
    while i < total_tokens:
        word = tokens[i]
        is_negated = False

        if i > 0 and tokens[i - 1] in negator_set:
            is_negated = True

        if word in pos_set:
            if is_negated:
                matched_negative.append(f"not {word}")
            else:
                matched_positive.append(word)
        elif word in neg_set:
            if is_negated:
                matched_positive.append(f"not {word}")
            else:
                matched_negative.append(word)

        i += 1

    pos_score = len(matched_positive)
    neg_score = len(matched_negative)
    net_score = pos_score - neg_score

    if total_tokens > 0:
        pos_ratio = pos_score / total_tokens
        neg_ratio = neg_score / total_tokens
        neutral_ratio = max(0.0, 1.0 - (pos_ratio + neg_ratio))
    else:
        pos_ratio = 0.0
        neg_ratio = 0.0
        neutral_ratio = 1.0

    if net_score > 0:
        overall = "Positive"
    elif net_score < 0:
        overall = "Negative"
    else:
        overall = "Neutral"

    return {
        "overall_sentiment": overall,
        "net_score": net_score,
        "positive_score": pos_score,
        "negative_score": neg_score,
        "total_words": total_tokens,
        "ratios": {
            "positive": round(pos_ratio, 4),
            "negative": round(neg_ratio, 4),
            "neutral": round(neutral_ratio, 4),
        },
        "matched_positive": matched_positive,
        "matched_negative": matched_negative,
    }


def load_custom_lexicon(filepath: Path) -> Tuple[Set[str], Set[str]]:
    """Load positive and negative word sets from a JSON file.

    JSON file format expected:
    {
        "positive": ["good", "great"],
        "negative": ["bad", "poor"]
    }
    """
    content = json.loads(filepath.read_text(encoding="utf-8"))
    pos = set(content.get("positive", []))
    neg = set(content.get("negative", []))
    return pos, neg


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Rule-based sentiment analyzer for text documents."
    parser = argparse.ArgumentParser(description=desc)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", type=str, help="Text string to analyze")
    group.add_argument("--file", type=Path, help="Path to text file to analyze")

    parser.add_argument(
        "--lexicon",
        type=Path,
        help="Optional path to custom lexicon JSON file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output result as formatted JSON",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Basic Sentiment Analyzer."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    pos_words = None
    neg_words = None

    if parsed.lexicon:
        if not parsed.lexicon.exists():
            sys.stderr.write(f"Error: Lexicon file '{parsed.lexicon}' not found.\n")
            return 1
        pos_words, neg_words = load_custom_lexicon(parsed.lexicon)

    if parsed.text:
        text_content = parsed.text
    else:
        if not parsed.file.exists():
            sys.stderr.write(f"Error: Text file '{parsed.file}' not found.\n")
            return 1
        text_content = parsed.file.read_text(encoding="utf-8")

    result = analyze_sentiment(
        text_content, positive_words=pos_words, negative_words=neg_words
    )

    if parsed.json_output:
        print(json.dumps(result, indent=2))
    else:
        pos_matches = result["matched_positive"]
        neg_matches = result["matched_negative"]
        ratios = result["ratios"]
        print("\n--- Sentiment Analysis Report ---")
        print(f"Overall Sentiment: {result['overall_sentiment']}")
        print(f"Net Score        : {result['net_score']}")
        print(f"Positive Matches : {result['positive_score']} {pos_matches}")
        print(f"Negative Matches : {result['negative_score']} {neg_matches}")
        print(
            f"Word Ratios      : Pos={ratios['positive']},"
            f" Neg={ratios['negative']}, Neu={ratios['neutral']}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

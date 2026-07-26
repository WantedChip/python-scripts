"""Keyword Extractor.

Extracts key terms and phrases from text documents using TF-IDF weighting
or term frequency scoring with stop-word filtering and N-gram support.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=dangerous-default-value

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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
    "shan't",
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


def tokenize(text: str) -> List[str]:
    """Extract lowercase word tokens from text."""
    return re.findall(r"\b[a-z]{2,}\b", text.lower())


def build_ngrams(words: List[str], n: int = 1) -> List[str]:
    """Generate n-gram sequence strings from a list of tokens."""
    if n <= 1:
        return words
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]  # noqa: E203


def is_valid_ngram(ng: str, stop_words: Set[str]) -> bool:
    """Check if n-gram phrase start or end is not a stop word."""
    parts = ng.split()
    return parts[0] not in stop_words and parts[-1] not in stop_words


def extract_keywords_tf(
    text: str,
    stop_words: Set[str] = DEFAULT_STOP_WORDS,
    ngram_size: int = 1,
    top_n: int = 10,
) -> List[Tuple[str, float]]:
    """Extract keywords using Term Frequency (TF) scoring.

    Args:
        text: Input text content.
        stop_words: Set of words to ignore.
        ngram_size: Size of n-grams (1 for unigrams, 2 for bigrams, etc.).
        top_n: Number of top keywords to return.

    Returns:
        List of tuples (keyword, frequency_score).
    """
    raw_words = tokenize(text)
    if ngram_size == 1:
        tokens = [w for w in raw_words if w not in stop_words]
    else:
        ngrams = build_ngrams(raw_words, ngram_size)
        tokens = [ng for ng in ngrams if is_valid_ngram(ng, stop_words)]

    total_tokens = len(tokens)
    if total_tokens == 0:
        return []

    counts = Counter(tokens)
    return [
        (kw, round(count / total_tokens, 4)) for kw, count in counts.most_common(top_n)
    ]


def extract_keywords_tfidf(
    documents: List[str],
    target_index: int = 0,
    stop_words: Set[str] = DEFAULT_STOP_WORDS,
    ngram_size: int = 1,
    top_n: int = 10,
) -> List[Tuple[str, float]]:
    """Extract keywords using TF-IDF weighting across a document corpus.

    Args:
        documents: List of document strings (corpus).
        target_index: Index of the target document in corpus.
        stop_words: Set of stop words to filter out.
        ngram_size: N-gram phrase length.
        top_n: Number of top keywords to return.

    Returns:
        List of tuples (keyword, tfidf_score).
    """
    if not documents or target_index >= len(documents):
        return []

    doc_tokens_list: List[List[str]] = []
    for doc in documents:
        raw_words = tokenize(doc)
        if ngram_size == 1:
            tokens = [w for w in raw_words if w not in stop_words]
        else:
            ngrams = build_ngrams(raw_words, ngram_size)
            tokens = [ng for ng in ngrams if is_valid_ngram(ng, stop_words)]
        doc_tokens_list.append(tokens)

    target_tokens = doc_tokens_list[target_index]
    total_target_tokens = len(target_tokens)
    if total_target_tokens == 0:
        return []

    target_counts = Counter(target_tokens)
    num_docs = len(documents)
    scores: Dict[str, float] = {}

    for term, count in target_counts.items():
        tf = count / total_target_tokens
        # Count documents containing term
        doc_freq = sum(1 for d_tokens in doc_tokens_list if term in d_tokens)
        idf = math.log((num_docs + 1) / (doc_freq + 1)) + 1.0
        scores[term] = round(tf * idf, 4)

    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return sorted_scores[:top_n]


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Extract top keywords from a document using TF or TF-IDF."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("file", type=Path, help="Path to text document")
    parser.add_argument(
        "--method",
        choices=["tf", "tfidf"],
        default="tf",
        help="Extraction method: tf or tfidf (default: tf)",
    )
    parser.add_argument(
        "--ngram",
        type=int,
        default=1,
        help="N-gram phrase size (1 for words, 2 for bigrams) (default: 1)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top keywords to return (default: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results in JSON format",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Keyword Extractor."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.file.exists():
        sys.stderr.write(f"Error: File '{parsed.file}' not found.\n")
        return 1

    text = parsed.file.read_text(encoding="utf-8")

    if parsed.method == "tf":
        keywords = extract_keywords_tf(text, ngram_size=parsed.ngram, top_n=parsed.top)
    else:
        # For single file TF-IDF, split text into paragraphs as corpus docs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) <= 1:
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        keywords = extract_keywords_tfidf(
            paragraphs,
            target_index=0,
            ngram_size=parsed.ngram,
            top_n=parsed.top,
        )

    if parsed.json_output:
        res = [{"keyword": k, "score": s} for k, s in keywords]
        print(json.dumps(res, indent=2))
    else:
        meth = parsed.method.upper()
        print(f"\n--- Top {len(keywords)} Keywords ({meth}, N-gram={parsed.ngram}) ---")
        for rank, (kw, score) in enumerate(keywords, start=1):
            print(f"{rank:2d}. {kw:<25} (score: {score})")

    return 0


if __name__ == "__main__":
    sys.exit(main())

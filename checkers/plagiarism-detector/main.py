"""Plagiarism Detector.

Compares two text documents and reports similarity metrics using N-gram
containment and TF-IDF / term frequency cosine distance.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase word sequence."""
    return re.findall(r"\b[a-zA-Z0-9']+\b", text.lower())


def generate_ngrams(words: List[str], n: int = 3) -> List[Tuple[str, ...]]:
    """Generate n-gram tuple sequences from a list of tokens."""
    if len(words) < n:
        return []
    return [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]  # noqa: E203


def calculate_jaccard_similarity(set1: Set[Any], set2: Set[Any]) -> float:
    """Calculate Jaccard similarity index between two sets."""
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union


def calculate_containment(source_ngrams: Set[Any], target_ngrams: Set[Any]) -> float:
    """Calculate N-gram containment (proportion of target n-grams found in source)."""
    if not target_ngrams:
        return 0.0
    intersection = len(target_ngrams.intersection(source_ngrams))
    return intersection / len(target_ngrams)


def calculate_cosine_similarity(words1: List[str], words2: List[str]) -> float:
    """Calculate Cosine Similarity between word frequency vectors of two texts.

    Args:
        words1: Tokens from document 1.
        words2: Tokens from document 2.

    Returns:
        Cosine similarity float (0.0 to 1.0).
    """
    if not words1 or not words2:
        return 0.0

    counts1 = Counter(words1)
    counts2 = Counter(words2)

    dot_product = sum(counts1[w] * counts2[w] for w in counts1 if w in counts2)
    mag1 = math.sqrt(sum(val**2 for val in counts1.values()))
    mag2 = math.sqrt(sum(val**2 for val in counts2.values()))

    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0

    return dot_product / (mag1 * mag2)


def find_matching_snippets(
    words1: List[str], words2: List[str], min_length: int = 3
) -> List[str]:
    """Identify matching word sequence snippets between two documents.

    Args:
        words1: Token list of first document.
        words2: Token list of second document.
        min_length: Minimum matching snippet length in words.

    Returns:
        List of matching phrase string snippets.
    """
    ngrams1 = set(generate_ngrams(words1, min_length))
    ngrams2 = generate_ngrams(words2, min_length)

    matches: Set[str] = set()
    for ng in ngrams2:
        if ng in ngrams1:
            matches.add(" ".join(ng))

    return sorted(list(matches))


def analyze_plagiarism(text1: str, text2: str, ngram_size: int = 3) -> Dict[str, Any]:
    """Perform comprehensive similarity analysis between two text documents.

    Args:
        text1: Original or reference text.
        text2: Target text to inspect.
        ngram_size: N-gram window size for containment checking.

    Returns:
        Dictionary containing similarity metrics and matching snippets.
    """
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)

    ngrams1 = set(generate_ngrams(tokens1, ngram_size))
    ngrams2 = set(generate_ngrams(tokens2, ngram_size))

    jaccard = calculate_jaccard_similarity(ngrams1, ngrams2)
    containment = calculate_containment(ngrams1, ngrams2)
    cosine_sim = calculate_cosine_similarity(tokens1, tokens2)

    # Composite similarity score (weighted average of cosine and containment)
    composite_similarity = (0.5 * cosine_sim) + (0.5 * containment)
    similarity_percentage = round(composite_similarity * 100, 2)

    snippets = find_matching_snippets(tokens1, tokens2, min_length=ngram_size)

    return {
        "similarity_percentage": similarity_percentage,
        "cosine_similarity": round(cosine_sim, 4),
        "ngram_containment": round(containment, 4),
        "jaccard_similarity": round(jaccard, 4),
        "ngram_size": ngram_size,
        "doc1_word_count": len(tokens1),
        "doc2_word_count": len(tokens2),
        "matching_snippets_count": len(snippets),
        "matching_snippets": snippets[:10],  # Top 10 snippets
    }


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = "Compare two text documents for similarity and potential plagiarism."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("file1", type=Path, help="Path to reference document")
    parser.add_argument("file2", type=Path, help="Path to document to analyze")
    parser.add_argument(
        "--ngram",
        type=int,
        default=3,
        help="N-gram window size for sequence matching (default: 3)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Plagiarism Detector."""
    parsed = parse_args(args)

    if not parsed.file1.exists() or not parsed.file2.exists():
        sys.stderr.write("Error: One or both specified files do not exist.\n")
        return 1

    t1 = parsed.file1.read_text(encoding="utf-8")
    t2 = parsed.file2.read_text(encoding="utf-8")

    report = analyze_plagiarism(t1, t2, ngram_size=parsed.ngram)

    if parsed.json_output:
        print(json.dumps(report, indent=2))
    else:
        print("\n=== Plagiarism & Similarity Report ===")
        print(f"Similarity Score       : {report['similarity_percentage']}%")
        print(f"Cosine Similarity      : {report['cosine_similarity']}")
        print(
            f"N-Gram Containment     : {report['ngram_containment']} "
            f"({parsed.ngram}-grams)"
        )
        print(f"Jaccard Index          : {report['jaccard_similarity']}")
        counts_str = (
            f"Doc1={report['doc1_word_count']}, " f"Doc2={report['doc2_word_count']}"
        )
        print(f"Word Counts            : {counts_str}")
        print(f"Matching Snippets Count: {report['matching_snippets_count']}")
        if report["matching_snippets"]:
            print("\nSample Matching Snippets:")
            for s in report["matching_snippets"]:
                print(f'  - "{s}"')

    return 0


if __name__ == "__main__":
    sys.exit(main())

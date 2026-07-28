"""Normalize text by expanding contractions, removing accents, and whitespace.

This module provides utilities to clean and standardize raw text files or
streams, making text ready for downstream processing, searching, or storage.
"""

import argparse
import logging
import re
import sys
import unicodedata
from typing import Dict, Pattern

# Configure module logger
logger = logging.getLogger(__name__)

# Dictionary of standard English contractions and their expanded forms
CONTRACTIONS: Dict[str, str] = {
    "aren't": "are not",
    "can't": "cannot",
    "could've": "could have",
    "couldn't": "could not",
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "hadn't": "had not",
    "hasn't": "has not",
    "haven't": "have not",
    "he'd": "he would",
    "he'll": "he will",
    "he's": "he is",
    "how'd": "how did",
    "how'll": "how will",
    "how's": "how is",
    "i'd": "i would",
    "i'll": "i will",
    "i'm": "i am",
    "i've": "i have",
    "isn't": "is not",
    "it'd": "it would",
    "it'll": "it will",
    "it's": "it is",
    "let's": "let us",
    "mightn't": "might not",
    "mustn't": "must not",
    "shan't": "shall not",
    "she'd": "she would",
    "she'll": "she will",
    "she's": "she is",
    "shouldn't": "should not",
    "that's": "that is",
    "there's": "there is",
    "they'd": "they would",
    "they'll": "they will",
    "they're": "they are",
    "they've": "they have",
    "wasn't": "was not",
    "we'd": "we would",
    "we'll": "we will",
    "we're": "we are",
    "we've": "we have",
    "weren't": "were not",
    "what'll": "what will",
    "what're": "what are",
    "what's": "what is",
    "what've": "what have",
    "where's": "where is",
    "who'd": "who would",
    "who'll": "who will",
    "who's": "who is",
    "who've": "who have",
    "won't": "will not",
    "wouldn't": "would not",
    "you'd": "you would",
    "you'll": "you will",
    "you're": "you are",
    "you've": "you have",
}

# Pre-compiled regex for smart quotes replacement
SMART_QUOTES_PATTERN: Pattern[str] = re.compile(r"[“”‘’`]")


def expand_contractions(text: str) -> str:
    """Expand common English contractions in text while preserving casing.

    Args:
        text: Input text string.

    Returns:
        Text string with expanded contractions.
    """

    def replace_contraction(match: re.Match[str]) -> str:
        word = match.group(0)
        word_lower = word.lower()

        # Check straight or curly apostrophe variants
        normalized_key = word_lower.replace("’", "'")
        if normalized_key in CONTRACTIONS:
            expanded = CONTRACTIONS[normalized_key]
            # Match original word casing (Capitalized or UPPERCASE)
            if word.isupper():
                return expanded.upper()
            if word[0].isupper():
                return expanded.capitalize()
            return expanded
        return word

    # Pattern matches words containing straight or curly apostrophes
    pattern = re.compile(
        r"\b[a-zA-Z]+['’][a-zA-Z]+\b",
        re.IGNORECASE,
    )
    return pattern.sub(replace_contraction, text)


def remove_accents(text: str) -> str:
    """Remove unicode diacritics and accent marks from text.

    Args:
        text: Input text string.

    Returns:
        ASCII-normalized text string without accents.
    """
    nfkd_form = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd_form if unicodedata.category(c) != "Mn")


def normalize_smart_quotes(text: str) -> str:
    """Convert smart / curly quotation marks and backticks to ASCII quotes.

    Args:
        text: Input text string.

    Returns:
        Text string with ASCII quotes.
    """
    mapping = {"“": '"', "”": '"', "‘": "'", "’": "'", "`": "'"}
    return SMART_QUOTES_PATTERN.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)


def standardize_whitespace(text: str, remove_extra_newlines: bool = False) -> str:
    """Standardize whitespace by trimming and collapsing multiple spaces.

    Args:
        text: Input text string.
        remove_extra_newlines: If True, collapse consecutive blank lines.

    Returns:
        Cleaned text string with standardized whitespace.
    """
    # Replace horizontal whitespace (tabs, non-breaking spaces) with single space
    lines = text.splitlines()
    cleaned_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]

    if remove_extra_newlines:
        filtered_lines = []
        last_empty = False
        for line in cleaned_lines:
            if not line:
                if not last_empty:
                    filtered_lines.append("")
                    last_empty = True
            else:
                filtered_lines.append(line)
                last_empty = False
        return "\n".join(filtered_lines)

    return "\n".join(cleaned_lines)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def normalize_text(
    text: str,
    expand: bool = True,
    no_accents: bool = True,
    clean_quotes: bool = True,
    clean_space: bool = True,
    lowercase: bool = False,
) -> str:
    """Apply full text normalization pipeline according to flags.

    Args:
        text: Input raw text string.
        expand: Expand contractions if True.
        no_accents: Remove accents if True.
        clean_quotes: Normalize smart quotes if True.
        clean_space: Standardize whitespace if True.
        lowercase: Lowercase entire text if True.

    Returns:
        Normalized output text string.
    """
    result = text

    if clean_quotes:
        result = normalize_smart_quotes(result)

    if expand:
        result = expand_contractions(result)

    if no_accents:
        result = remove_accents(result)

    if clean_space:
        result = standardize_whitespace(result)

    if lowercase:
        result = result.lower()

    return result


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Normalize text by expanding contractions, removing accents, "
            "and standardizing whitespace."
        )
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=argparse.FileType("r", encoding="utf-8"),
        default=sys.stdin,
        help="Input text file path (defaults to stdin).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=argparse.FileType("w", encoding="utf-8"),
        default=sys.stdout,
        help="Output text file path (defaults to stdout).",
    )
    parser.add_argument(
        "--no-contractions",
        action="store_true",
        help="Disable contraction expansion.",
    )
    parser.add_argument(
        "--keep-accents",
        action="store_true",
        help="Preserve unicode accents and diacritics.",
    )
    parser.add_argument(
        "-l",
        "--lowercase",
        action="store_true",
        help="Convert output text to lowercase.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def main() -> None:
    """Main CLI execution entry point."""
    parser = setup_cli_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    try:
        content = args.file.read()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to read input text: %s", exc)
        sys.exit(1)

    normalized = normalize_text(
        content,
        expand=not args.no_contractions,
        no_accents=not args.keep_accents,
        lowercase=args.lowercase,
    )

    try:
        args.output.write(normalized)
        if args.output != sys.stdout:
            args.output.write("\n")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to write output text: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

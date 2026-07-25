"""Text Case Converter.

Converts text files or strings between lowercase, uppercase, title case,
camelCase, snake_case, sentence case, and kebab-case.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-return-statements

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional


def split_into_words(text: str) -> List[str]:
    """Splits a string or identifier into constituent words."""
    # Insert space before capital letters in camelCase / PascalCase
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    # Replace non-alphanumeric characters with space
    s2 = re.sub(r"[^\w\s]", " ", s1)
    # Replace underscores with space
    s3 = s2.replace("_", " ")
    # Split by whitespace
    words = [w for w in s3.split() if w]
    return words


def to_lowercase(text: str) -> str:
    """Converts entire text to lowercase."""
    return text.lower()


def to_uppercase(text: str) -> str:
    """Converts entire text to uppercase."""
    return text.upper()


def to_titlecase(text: str) -> str:
    """Converts text to Title Case."""
    return text.title()


def to_camelcase(text: str) -> str:
    """Converts text or identifiers to camelCase."""
    lines = text.splitlines(keepends=True)
    res_lines = []
    for line in lines:
        words = split_into_words(line)
        if not words:
            res_lines.append(line)
            continue
        first = words[0].lower()
        rest = [w.capitalize() for w in words[1:]]
        converted = first + "".join(rest)
        # Preserve original trailing newline if any
        ending = "\n" if line.endswith("\n") else ""
        res_lines.append(converted + ending)
    return "".join(res_lines)


def to_snakecase(text: str) -> str:
    """Converts text or identifiers to snake_case."""
    lines = text.splitlines(keepends=True)
    res_lines = []
    for line in lines:
        words = split_into_words(line)
        if not words:
            res_lines.append(line)
            continue
        converted = "_".join(w.lower() for w in words)
        ending = "\n" if line.endswith("\n") else ""
        res_lines.append(converted + ending)
    return "".join(res_lines)


def to_kebabcase(text: str) -> str:
    """Converts text or identifiers to kebab-case."""
    lines = text.splitlines(keepends=True)
    res_lines = []
    for line in lines:
        words = split_into_words(line)
        if not words:
            res_lines.append(line)
            continue
        converted = "-".join(w.lower() for w in words)
        ending = "\n" if line.endswith("\n") else ""
        res_lines.append(converted + ending)
    return "".join(res_lines)


def to_sentencecase(text: str) -> str:
    """Converts text to Sentence case."""
    lines = text.splitlines(keepends=True)
    res_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            res_lines.append(line)
            continue
        # Capitalize first letter of each sentence separated by . ! ?
        sentences = re.split(r"([.!?]+\s*)", line)
        reconstructed = []
        for part in sentences:
            if part and not re.match(r"^[.!?]+\s*$", part):
                # Sentence fragment
                leading_spaces = len(part) - len(part.lstrip())
                trimmed = part.strip()
                if trimmed:
                    cap = trimmed[0].upper() + trimmed[1:].lower()
                    reconstructed.append(" " * leading_spaces + cap)
                else:
                    reconstructed.append(part)
            else:
                reconstructed.append(part)
        res_lines.append("".join(reconstructed))
    return "".join(res_lines)


def convert_text(text: str, mode: str) -> str:
    """Applies the requested case conversion mode to text."""
    mode = mode.lower()
    if mode in ["lower", "lowercase"]:
        return to_lowercase(text)
    if mode in ["upper", "uppercase"]:
        return to_uppercase(text)
    if mode in ["title", "titlecase"]:
        return to_titlecase(text)
    if mode in ["camel", "camelcase"]:
        return to_camelcase(text)
    if mode in ["snake", "snakecase"]:
        return to_snakecase(text)
    if mode in ["kebab", "kebabcase"]:
        return to_kebabcase(text)
    if mode in ["sentence", "sentencecase"]:
        return to_sentencecase(text)
    raise ValueError(f"Unsupported conversion mode: '{mode}'")


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Text Case Converter")
    parser.add_argument(
        "input_file",
        nargs="?",
        type=str,
        default=None,
        help="Path to input file (or stdin if omitted)",
    )
    parser.add_argument(
        "--mode",
        "-m",
        required=True,
        choices=[
            "lower",
            "lowercase",
            "upper",
            "uppercase",
            "title",
            "titlecase",
            "camel",
            "camelcase",
            "snake",
            "snakecase",
            "kebab",
            "kebabcase",
            "sentence",
            "sentencecase",
        ],
        help="Target casing transformation mode",
    )
    parser.add_argument(
        "--in-place",
        "-i",
        action="store_true",
        help="Modify input file in-place",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output file path (default: stdout)",
    )
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point for text-case-converter."""
    parsed = parse_args(args)

    if parsed.input_file:
        input_path = Path(parsed.input_file)
        if not input_path.exists():
            print(f"Error: File not found '{input_path}'", file=sys.stderr)
            return 1
        text = input_path.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty() and not parsed.input_file:
            msg = "Error: No input file specified and stdin is interactive."
            print(msg, file=sys.stderr)
            return 1
        text = sys.stdin.read()

    try:
        converted = convert_text(text, parsed.mode)
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    if parsed.in_place:
        if not parsed.input_file:
            print("Error: Cannot use --in-place with stdin.", file=sys.stderr)
            return 1
        Path(parsed.input_file).write_text(converted, encoding="utf-8")
        print(f"Successfully converted '{parsed.input_file}' in-place.")
    elif parsed.output:
        Path(parsed.output).write_text(converted, encoding="utf-8")
        print(f"Successfully wrote output to '{parsed.output}'.")
    else:
        print(converted, end="")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Identify and highlight named entities in text using regex patterns.

This module extracts and highlights Names, Dates, Organizations, and Locations
in text documents using rule-based regular expressions. It supports multiple
output formats including ANSI terminal colors, HTML markup, Markdown, and JSON.
"""

import argparse
import html
import json
import logging
import re
import sys
from typing import Any, Dict, List, NamedTuple, Pattern, Tuple

# Configure module logger
logger = logging.getLogger(__name__)

# Regular Expression Patterns for Entity Recognition

# 1. Dates
DATE_PATTERN: Pattern[str] = re.compile(
    r"\b(?:"
    r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"  # YYYY-MM-DD
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"  # MM/DD/YYYY
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*,\s*\d{4})?"  # Month DD, YYYY
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"(?:\s+\d{4})?"  # DD Month YYYY
    r")\b",
    re.IGNORECASE,
)

# 2. Organizations
ORG_PATTERN: Pattern[str] = re.compile(
    r"\b[A-Z][a-zA-Z0-9&'-]+(?:\s+[A-Z][a-zA-Z0-9&'-]+)*\s+"
    r"(?:Corp(?:oration)?|Inc(?:orporated)?|Ltd|LLC|Group|University|College|"
    r"Foundation|Association|Institute|Co|Company|Agency|Department|Bank|Systems)\b"
)

# 3. Names (with titles/honorifics or 2-3 capitalized words)
NAME_PATTERN: Pattern[str] = re.compile(
    r"\b(?:Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.|Sir|Lady|President|Gov\.)\s+"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b"
    r"|\b[A-Z][a-z]+\s+(?:[A-Z]\.\s+)?[A-Z][a-z]+\b"
)

# 4. Locations (Geographic suffixes or indicators)
LOCATION_PATTERN: Pattern[str] = re.compile(
    r"\b(?:Mount|Mt\.|Lake|River|San|Santa|New|Fort|Port|St\.|Saint)\s+"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
    r"|\b[A-Z][a-z]+\s+(?:City|State|Island|Islands|Ocean|Sea|Bay|Valley|Street|"
    r"Avenue|Road|Drive|Park|County|Kingdom|Republic)\b"
)

# ANSI Color Codes
ANSI_COLORS: Dict[str, str] = {
    "NAME": "\033[94m",  # Blue
    "DATE": "\033[92m",  # Green
    "ORG": "\033[93m",  # Yellow
    "LOCATION": "\033[95m",  # Magenta
    "RESET": "\033[0m",
}


class EntityMatch(NamedTuple):
    """Container for matched entity data."""

    text: str
    label: str
    start: int
    end: int


def extract_entities(text: str) -> List[EntityMatch]:
    """Find non-overlapping entity occurrences sorted by character offset.

    Args:
        text: Input raw text string.

    Returns:
        List of EntityMatch objects sorted by start position.
    """
    raw_matches: List[Tuple[int, int, str, str]] = []

    # Priority matching: ORG -> LOCATION -> DATE -> NAME
    for m in ORG_PATTERN.finditer(text):
        raw_matches.append((m.start(), m.end(), m.group(0), "ORG"))

    for m in LOCATION_PATTERN.finditer(text):
        raw_matches.append((m.start(), m.end(), m.group(0), "LOCATION"))

    for m in DATE_PATTERN.finditer(text):
        raw_matches.append((m.start(), m.end(), m.group(0), "DATE"))

    for m in NAME_PATTERN.finditer(text):
        raw_matches.append((m.start(), m.end(), m.group(0), "NAME"))

    # Sort matches by start index, preferring longer matches on overlap
    raw_matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    filtered_matches: List[EntityMatch] = []
    last_end = 0

    for start, end, match_text, label in raw_matches:
        if start >= last_end:
            filtered_matches.append(
                EntityMatch(text=match_text, label=label, start=start, end=end)
            )
            last_end = end

    return filtered_matches


def highlight_ansi(text: str, entities: List[EntityMatch]) -> str:
    """Format text with ANSI color sequences for terminal output.

    Args:
        text: Original text string.
        entities: List of sorted EntityMatch objects.

    Returns:
        ANSI-colored text string.
    """
    if not entities:
        return text

    out_parts: List[str] = []
    last_idx = 0

    for ent in entities:
        out_parts.append(text[last_idx : ent.start])  # noqa: E203
        color = ANSI_COLORS.get(ent.label, "")
        out_parts.append(f"{color}{ent.text}{ANSI_COLORS['RESET']}")
        last_idx = ent.end

    out_parts.append(text[last_idx:])
    return "".join(out_parts)


def highlight_html(text: str, entities: List[EntityMatch]) -> str:
    """Format text with HTML span markup for web rendering.

    Args:
        text: Original text string.
        entities: List of sorted EntityMatch objects.

    Returns:
        HTML string with highlighted entities.
    """
    if not entities:
        return html.escape(text)

    out_parts: List[str] = []
    last_idx = 0

    for ent in entities:
        out_parts.append(html.escape(text[last_idx : ent.start]))  # noqa: E203
        css_class = f"entity-{ent.label.lower()}"
        escaped_val = html.escape(ent.text)
        out_parts.append(
            f'<mark class="{css_class}" data-entity="{ent.label}">{escaped_val}</mark>'
        )
        last_idx = ent.end

    out_parts.append(html.escape(text[last_idx:]))
    return "".join(out_parts)


def highlight_markdown(text: str, entities: List[EntityMatch]) -> str:
    """Format text with Markdown bold and tag annotations.

    Args:
        text: Original text string.
        entities: List of sorted EntityMatch objects.

    Returns:
        Markdown string with inline entity tags.
    """
    if not entities:
        return text

    out_parts: List[str] = []
    last_idx = 0

    for ent in entities:
        out_parts.append(text[last_idx : ent.start])  # noqa: E203
        out_parts.append(f"**{ent.text}**`[{ent.label}]`")
        last_idx = ent.end

    out_parts.append(text[last_idx:])
    return "".join(out_parts)


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Identify and highlight names, dates, organizations, and "
            "locations in text using regex."
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
        "-f",
        "--format",
        choices=["ansi", "html", "markdown", "json"],
        default="ansi",
        help="Output highlight format (default: ansi).",
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

    entities = extract_entities(content)

    if args.format == "json":
        json_output: List[Dict[str, Any]] = [
            {
                "entity": e.text,
                "label": e.label,
                "start": e.start,
                "end": e.end,
            }
            for e in entities
        ]
        print(json.dumps(json_output, indent=2))
    elif args.format == "html":
        print(highlight_html(content, entities))
    elif args.format == "markdown":
        print(highlight_markdown(content, entities))
    else:
        print(highlight_ansi(content, entities))


if __name__ == "__main__":
    main()

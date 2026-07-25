"""Book Info Scraper.

Looks up book metadata (title, author, published date, description, ratings)
by ISBN using the Open Library API. Supports ISBN-10 and ISBN-13 validation,
terminal card formatting, and exporting to JSON or Markdown formats.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-instance-attributes
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple, cast


@dataclass
class BookMetadata:
    """Dataclass holding normalized book metadata."""

    isbn: str
    isbn_type: str
    title: str
    authors: List[str]
    publish_date: str
    publishers: List[str]
    number_of_pages: Optional[int]
    subjects: List[str]
    cover_url: Optional[str]
    openlibrary_url: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return asdict(self)


def clean_isbn(isbn: str) -> str:
    """Remove hyphens, spaces, and convert check character to uppercase.

    Args:
        isbn: Raw ISBN string.

    Returns:
        Sanitized ISBN string.
    """
    return re.sub(r"[\s\-]", "", isbn).strip().upper()


def validate_isbn_10(isbn: str) -> bool:
    """Validate an ISBN-10 number using check digit algorithm.

    Args:
        isbn: Sanitized 10-character ISBN string.

    Returns:
        True if valid ISBN-10, False otherwise.
    """
    if len(isbn) != 10:
        return False
    if not re.match(r"^\d{9}[\dX]$", isbn):
        return False

    total = 0
    for i in range(9):
        total += int(isbn[i]) * (10 - i)

    check = 10 if isbn[9] == "X" else int(isbn[9])
    total += check

    return total % 11 == 0


def validate_isbn_13(isbn: str) -> bool:
    """Validate an ISBN-13 number using check digit algorithm.

    Args:
        isbn: Sanitized 13-character ISBN string.

    Returns:
        True if valid ISBN-13, False otherwise.
    """
    if len(isbn) != 13 or not isbn.isdigit():
        return False

    total = 0
    for i in range(12):
        weight = 1 if i % 2 == 0 else 3
        total += int(isbn[i]) * weight

    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(isbn[12])


def validate_isbn(isbn_str: str) -> Tuple[bool, str, str]:
    """Validate ISBN format and return status, type, and sanitized string.

    Args:
        isbn_str: Input ISBN string.

    Returns:
        Tuple of (is_valid, isbn_type, cleaned_isbn).
    """
    cleaned = clean_isbn(isbn_str)
    if len(cleaned) == 10 and validate_isbn_10(cleaned):
        return True, "ISBN-10", cleaned
    if len(cleaned) == 13 and validate_isbn_13(cleaned):
        return True, "ISBN-13", cleaned
    return False, "UNKNOWN", cleaned


def fetch_open_library_data(isbn: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Fetch raw book data from Open Library API.

    Args:
        isbn: Validated sanitized ISBN string.
        timeout: Request timeout in seconds.

    Returns:
        Dictionary of API response data or None if request fails.
    """
    base_url = "https://openlibrary.org/api/books"
    url = f"{base_url}?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    req = urllib.request.Request(
        url, headers={"User-Agent": "BookInfoScraper/1.0 (Python)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                bib_key = f"ISBN:{isbn}"
                return cast(Optional[Dict[str, Any]], data.get(bib_key))
    except (urllib.error.URLError, json.JSONDecodeError, OSError, ValueError):
        return None
    return None


def parse_book_metadata(
    isbn: str, isbn_type: str, raw_data: Dict[str, Any]
) -> BookMetadata:
    """Parse Open Library raw API response into a structured BookMetadata.

    Args:
        isbn: Sanitized ISBN string.
        isbn_type: ISBN format type (ISBN-10 or ISBN-13).
        raw_data: Raw JSON payload from Open Library.

    Returns:
        Populated BookMetadata dataclass.
    """
    title = raw_data.get("title", "Unknown Title")

    authors = []
    for author in raw_data.get("authors", []):
        if isinstance(author, dict) and "name" in author:
            authors.append(author["name"])
    if not authors:
        authors = ["Unknown Author"]

    publishers = []
    for pub in raw_data.get("publishers", []):
        if isinstance(pub, dict) and "name" in pub:
            publishers.append(pub["name"])
        elif isinstance(pub, str):
            publishers.append(pub)

    publish_date = raw_data.get("publish_date", "Unknown Date")
    number_of_pages = raw_data.get("number_of_pages")

    subjects = []
    for subj in raw_data.get("subjects", [])[:10]:
        if isinstance(subj, dict) and "name" in subj:
            subjects.append(subj["name"])
        elif isinstance(subj, str):
            subjects.append(subj)

    cover = raw_data.get("cover", {})
    cover_url = cover.get("large") or cover.get("medium") or cover.get("small")

    openlibrary_url = raw_data.get("url")

    return BookMetadata(
        isbn=isbn,
        isbn_type=isbn_type,
        title=title,
        authors=authors,
        publish_date=publish_date,
        publishers=publishers,
        number_of_pages=number_of_pages,
        subjects=subjects,
        cover_url=cover_url,
        openlibrary_url=openlibrary_url,
    )


def format_terminal_card(book: BookMetadata) -> str:
    """Format book metadata into an ASCII terminal card layout.

    Args:
        book: BookMetadata object.

    Returns:
        Formatted multi-line card string.
    """
    width = 64
    border = "=" * width
    divider = "-" * width

    publishers_str = ", ".join(book.publishers) if book.publishers else "N/A"
    pages_str = str(book.number_of_pages) if book.number_of_pages else "N/A"
    subjects_str = ", ".join(book.subjects[:5]) if book.subjects else "N/A"

    lines = [
        border,
        f" BOOK INFORMATION ({book.isbn_type}: {book.isbn})".center(width),
        border,
        f" Title        : {book.title}",
        f" Author(s)    : {', '.join(book.authors)}",
        f" Published   : {book.publish_date}",
        f" Publisher(s) : {publishers_str}",
        f" Pages        : {pages_str}",
        divider,
        f" Subjects     : {subjects_str}",
        f" Cover URL    : {book.cover_url or 'N/A'}",
        f" OL Link      : {book.openlibrary_url or 'N/A'}",
        border,
    ]
    return "\n".join(lines)


def format_markdown(book: BookMetadata) -> str:
    """Format book metadata into Markdown summary.

    Args:
        book: BookMetadata object.

    Returns:
        Markdown formatted document.
    """
    authors_str = ", ".join(book.authors)
    publishers_str = ", ".join(book.publishers) if book.publishers else "N/A"
    if book.subjects:
        subjects_str = ", ".join(f"`{s}`" for s in book.subjects)
    else:
        subjects_str = "N/A"

    md_lines = [
        f"# {book.title}",
        "",
        f"**Author(s):** {authors_str}  ",
        f"**ISBN ({book.isbn_type}):** `{book.isbn}`  ",
        f"**Publication Date:** {book.publish_date}  ",
        f"**Publisher:** {publishers_str}  ",
        f"**Pages:** {book.number_of_pages or 'N/A'}  ",
        "",
        "## Subjects",
        subjects_str,
        "",
    ]
    if book.cover_url:
        md_lines.extend([f"![Book Cover]({book.cover_url})", ""])
    if book.openlibrary_url:
        md_lines.extend([f"[Open Library Profile]({book.openlibrary_url})", ""])

    return "\n".join(md_lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Lookup book metadata by ISBN using Open Library API."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "isbn",
        type=str,
        help="ISBN-10 or ISBN-13 code (with or without hyphens)",
    )
    parser.add_argument(
        "--format",
        choices=["terminal", "json", "markdown"],
        default="terminal",
        help="Output format (default: terminal)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="File path to save the output",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Book Info Scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    is_valid, isbn_type, cleaned_isbn = validate_isbn(parsed.isbn)
    if not is_valid:
        msg = f"Error: '{parsed.isbn}' is not a valid ISBN-10 or " "ISBN-13 identifier."
        print(msg, file=sys.stderr)
        return 1

    raw_data = fetch_open_library_data(cleaned_isbn)
    if not raw_data:
        msg = f"Error: No metadata found on Open Library for ISBN " f"{cleaned_isbn}."
        print(msg, file=sys.stderr)
        return 1

    book = parse_book_metadata(cleaned_isbn, isbn_type, raw_data)

    if parsed.format == "json":
        output_str = json.dumps(book.to_dict(), indent=2)
    elif parsed.format == "markdown":
        output_str = format_markdown(book)
    else:
        output_str = format_terminal_card(book)

    if parsed.output:
        with open(parsed.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Book info saved to {parsed.output}")
    else:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())

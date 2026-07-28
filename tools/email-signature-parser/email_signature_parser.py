"""Extract contact information from email signature blocks.

This module provides tools to parse text blocks representing email signatures
and extract key details such as names, titles, phone numbers, email addresses,
websites, addresses, and social profiles using robust regular expressions.
"""

import argparse
import json
import logging
import re
import sys
from typing import Any, Dict, List, Optional, Pattern, cast

# Configure module logger
logger = logging.getLogger(__name__)

# Regular expression patterns for extraction
EMAIL_PATTERN: Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)

PHONE_PATTERN: Pattern[str] = re.compile(
    r"(?:(?:\+|00)\d{1,3}[\s.-]?)?"  # Country code
    r"(?:\(?\d{2,5}\)?[\s.-]?)?"  # Area code
    r"\d{3,4}[\s.-]?\d{3,4}"  # Main number
    r"(?:\s*(?:ext|x|ext\.)\s*\d+)?"  # Extension
    r"(?=\b|\s|$)",
    re.IGNORECASE,
)

URL_PATTERN: Pattern[str] = re.compile(r"https?://[^\s>]+|www\.[^\s>]+", re.IGNORECASE)

TITLE_KEYWORDS: List[str] = [
    "engineer",
    "developer",
    "manager",
    "director",
    "executive",
    "president",
    "vice president",
    "vp",
    "ceo",
    "cto",
    "cfo",
    "coo",
    "lead",
    "head",
    "architect",
    "specialist",
    "consultant",
    "analyst",
    "officer",
    "founder",
    "co-founder",
    "administrator",
    "coordinator",
    "supervisor",
    "designer",
]


def extract_emails(text: str) -> List[str]:
    """Extract email addresses from text block.

    Args:
        text: The input signature text.

    Returns:
        List of extracted unique email address strings.
    """
    matches = EMAIL_PATTERN.findall(text)
    seen = set()
    result: List[str] = []
    for email in matches:
        email_clean = email.strip()
        if email_clean.lower() not in seen:
            seen.add(email_clean.lower())
            result.append(email_clean)
    return result


def extract_phones(text: str) -> List[str]:
    """Extract phone numbers from text block.

    Args:
        text: The input signature text.

    Returns:
        List of extracted phone number strings.
    """
    matches = PHONE_PATTERN.findall(text)
    result: List[str] = []
    seen = set()
    for match in matches:
        phone_clean = match.strip(" .,;-:")
        # Filter out short numbers or pure dates like 2026-07-28
        digits = re.sub(r"\D", "", phone_clean)
        if len(digits) >= 7 and phone_clean not in seen:
            seen.add(phone_clean)
            result.append(phone_clean)
    return result


def extract_urls(text: str) -> List[str]:
    """Extract website URLs and social links from text block.

    Args:
        text: The input signature text.

    Returns:
        List of extracted URL strings.
    """
    matches = URL_PATTERN.findall(text)
    result: List[str] = []
    seen = set()
    for match in matches:
        url_clean = match.strip(" .,;:-")
        if url_clean.lower() not in seen:
            seen.add(url_clean.lower())
            result.append(url_clean)
    return result


def extract_title(lines: List[str]) -> Optional[str]:
    """Extract candidate job title from lines of text.

    Args:
        lines: List of non-empty signature lines.

    Returns:
        Extracted job title string if found, otherwise None.
    """
    for line in lines:
        line_clean = line.strip()
        # Skip line if it contains email or URL
        if EMAIL_PATTERN.search(line_clean) or URL_PATTERN.search(line_clean):
            continue

        line_lower = line_clean.lower()
        if any(keyword in line_lower for keyword in TITLE_KEYWORDS):
            return line_clean

    return None


def extract_name(lines: List[str], title: Optional[str]) -> Optional[str]:
    """Extract candidate person name from initial lines of text.

    Args:
        lines: List of non-empty signature lines.
        title: Previously identified title to avoid returning title as name.

    Returns:
        Candidate person name string if found, otherwise None.
    """
    salutations = [
        "best",
        "regards",
        "thanks",
        "sincerely",
        "cheers",
        "kind regards",
    ]

    for line in lines:
        line_clean = line.strip()
        # Strip sign-off prefixes like "Best regards," or "Thanks,"
        for sal in salutations:
            if line_clean.lower().startswith(sal):
                line_clean = re.sub(
                    rf"^{sal}[,:\s]*", "", line_clean, flags=re.IGNORECASE
                ).strip()

        if not line_clean:
            continue

        # Skip lines with emails, phones, or URLs
        if (
            EMAIL_PATTERN.search(line_clean)
            or URL_PATTERN.search(line_clean)
            or PHONE_PATTERN.search(line_clean)
        ):
            continue

        if title and line_clean == title:
            continue

        # Simple heuristic: Name is typically 2-4 words, capitalized letters
        words = line_clean.split()
        is_name_pattern = re.match(
            r"^[A-Z][a-zA-Z\.\'-]+(?:\s+[A-Z][a-zA-Z\.\'-]+)*$", line_clean
        )
        if 1 <= len(words) <= 4 and is_name_pattern:
            return line_clean

    return None


def parse_signature(signature_text: str) -> Dict[str, Any]:
    """Parse signature text into a structured dictionary.

    Args:
        signature_text: Full raw email signature text.

    Returns:
        Dictionary containing extracted fields (name, title, emails, phones, urls).
    """
    raw_lines = signature_text.splitlines()
    cleaned_lines = [line.strip() for line in raw_lines if line.strip()]

    emails = extract_emails(signature_text)
    phones = extract_phones(signature_text)
    urls = extract_urls(signature_text)
    title = extract_title(cleaned_lines)
    name = extract_name(cleaned_lines, title)

    return {
        "name": name,
        "title": title,
        "emails": emails,
        "phones": phones,
        "urls": urls,
    }


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Extract contact details from email signature blocks."
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=argparse.FileType("r", encoding="utf-8"),
        default=sys.stdin,
        help="Input text file containing signature (defaults to stdin).",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output extracted information in JSON format.",
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
        logger.error("Failed to read input: %s", exc)
        sys.exit(1)

    parsed_data: Dict[str, Any]
    if not content.strip():
        logger.warning("Input signature text is empty.")
        parsed_data = {
            "name": None,
            "title": None,
            "emails": [],
            "phones": [],
            "urls": [],
        }
    else:
        parsed_data = parse_signature(content)

    if args.json:
        print(json.dumps(parsed_data, indent=2))
    else:
        emails_str = ", ".join(cast(List[str], parsed_data["emails"]))
        phones_str = ", ".join(cast(List[str], parsed_data["phones"]))
        urls_str = ", ".join(cast(List[str], parsed_data["urls"]))

        print("--- Extracted Signature Info ---")
        print(f"Name:   {parsed_data['name'] or 'N/A'}")
        print(f"Title:  {parsed_data['title'] or 'N/A'}")
        print(f"Emails: {emails_str or 'None'}")
        print(f"Phones: {phones_str or 'None'}")
        print(f"URLs:   {urls_str or 'None'}")


if __name__ == "__main__":
    main()

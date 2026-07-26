"""Reading Time Estimator.

Calculates estimated reading time for local text files or HTTP/HTTPS URLs based
on word count and configurable Words Per Minute (WPM) settings.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import math
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

IGNORE_TAGS = {"script", "style", "head", "title", "meta", "noscript"}


class HTMLTextExtractor(HTMLParser):
    """Simple HTML parser to extract clean text content from HTML documents."""

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: List[str] = []
        self._ignore: bool = False

    def handle_starttag(self, tag: str, attrs: List[Any]) -> None:
        if tag.lower() in IGNORE_TAGS:
            self._ignore = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in IGNORE_TAGS:
            self._ignore = False

    def handle_data(self, data: str) -> None:
        if not self._ignore:
            cleaned = data.strip()
            if cleaned:
                self.text_parts.append(cleaned)

    def get_text(self) -> str:
        """Return all extracted text joined by spaces."""
        return " ".join(self.text_parts)


def clean_html(html_content: str) -> str:
    """Extract plain text content from HTML string using HTMLParser fallback."""
    parser = HTMLTextExtractor()
    try:
        parser.feed(html_content)
        return parser.get_text()
    except Exception:  # pylint: disable=broad-exception-caught
        # Fallback simple regex tag stripping if HTMLParser encounters issue
        return re.sub(r"<[^>]+>", " ", html_content)


def count_words(text: str) -> int:
    """Count the total number of words in a given text string.

    Args:
        text: Plain text input string.

    Returns:
        Integer count of words.
    """
    words = re.findall(r"\b\w+\b", text)
    return len(words)


def fetch_url_text(url: str, timeout: int = 10) -> str:
    """Fetch text content from a web URL.

    Args:
        url: Valid HTTP or HTTPS URL.
        timeout: Network request timeout in seconds.

    Returns:
        Extracted text content from the URL.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "ReadingTimeEstimator/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
        content_type = response.headers.get("Content-Type", "")
        raw_bytes = response.read()
        encoding = response.headers.get_param("charset") or "utf-8"
        raw_text = raw_bytes.decode(encoding, errors="replace")

        if "html" in content_type.lower() or "<html" in raw_text.lower():
            return str(clean_html(raw_text))
        return str(raw_text)


def estimate_reading_time(
    text: str, wpm: int = 200
) -> Dict[str, Union[int, float, str]]:
    """Calculate reading time estimate for input text.

    Args:
        text: Plain text content.
        wpm: Words Per Minute reading speed (default: 200).

    Returns:
        Dictionary containing word_count, total_seconds, minutes, and
        formatted time string.
    """
    if wpm <= 0:
        raise ValueError("Words Per Minute (wpm) must be a positive integer.")

    word_count = count_words(text)
    total_seconds = math.ceil((word_count / wpm) * 60) if word_count > 0 else 0

    minutes = total_seconds // 60
    seconds = total_seconds % 60

    if minutes == 0 and seconds == 0:
        formatted = "0 seconds"
    elif minutes == 0:
        formatted = f"{seconds} sec"
    elif seconds == 0:
        formatted = f"{minutes} min"
    else:
        formatted = f"{minutes} min {seconds} sec"

    return {
        "word_count": word_count,
        "wpm": wpm,
        "total_seconds": total_seconds,
        "minutes": minutes,
        "seconds": seconds,
        "formatted": formatted,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Estimate reading time for local text files or web URLs."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "source",
        type=str,
        help="Path to local file or valid HTTP/HTTPS URL",
    )
    parser.add_argument(
        "--wpm",
        type=int,
        default=200,
        help="Reading speed in Words Per Minute (default: 200)",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Reading Time Estimator."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    try:
        src = parsed.source
        if src.startswith("http://") or src.startswith("https://"):
            print(f"Fetching content from URL: {src}...")
            content = fetch_url_text(src)
        else:
            file_path = Path(src)
            if not file_path.exists():
                sys.stderr.write(f"Error: File '{src}' does not exist.\n")
                return 1
            raw_content = file_path.read_text(encoding="utf-8")
            if file_path.suffix.lower() in (".html", ".htm"):
                content = clean_html(raw_content)
            else:
                content = raw_content

        result = estimate_reading_time(content, wpm=parsed.wpm)

        print("\n--- Reading Time Estimation ---")
        print(f"Word Count      : {result['word_count']} words")
        print(f"Reading Speed   : {result['wpm']} WPM")
        fmt = result["formatted"]
        tot_sec = result["total_seconds"]
        print(f"Estimated Time  : {fmt} ({tot_sec} seconds)")

    except (OSError, ValueError, urllib.error.URLError) as err:
        sys.stderr.write(f"Error processing input: {err}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Product Review Scraper.

Extracts product reviews (rating, author, date, review text, verified status)
from HTML web pages or JSON-LD review structures, calculates rating
distribution statistics, cleans review body text, and exports structured CSV
or JSON data.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import csv
import html.parser
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Review:
    """Dataclass holding extracted product review fields."""

    review_id: str
    author: str
    rating: float
    date: str
    title: str
    text: str
    verified: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert review object to dictionary."""
        return asdict(self)


@dataclass
class ReviewStats:
    """Dataclass holding aggregated review statistics."""

    total_reviews: int
    average_rating: float
    rating_distribution: Dict[int, int]  # {1: count, 2: count, ..., 5: count}
    verified_count: int
    verified_percentage: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return asdict(self)


def clean_review_text(text: str) -> str:
    """Clean and normalize review body text for downstream NLP / sentiment.

    Args:
        text: Raw review text string.

    Returns:
        Sanitized and trimmed text.
    """
    if not text:
        return ""
    # Strip HTML tags if present
    clean = re.sub(r"<[^>]+>", " ", text)
    # Unescape HTML entities (basic)
    clean = (
        clean.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    # Normalize multiple whitespace, tabs, newlines
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def calculate_review_stats(reviews: List[Review]) -> ReviewStats:
    """Compute summary statistics for a collection of reviews.

    Args:
        reviews: List of Review dataclass instances.

    Returns:
        Populated ReviewStats instance.
    """
    if not reviews:
        return ReviewStats(
            total_reviews=0,
            average_rating=0.0,
            rating_distribution={1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            verified_count=0,
            verified_percentage=0.0,
        )

    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total_rating = 0.0
    verified_count = 0

    for r in reviews:
        total_rating += r.rating
        star = max(1, min(5, int(round(r.rating))))
        dist[star] += 1
        if r.verified:
            verified_count += 1

    avg_rating = round(total_rating / len(reviews), 2)
    verified_pct = round((verified_count / len(reviews)) * 100.0, 1)

    return ReviewStats(
        total_reviews=len(reviews),
        average_rating=avg_rating,
        rating_distribution=dist,
        verified_count=verified_count,
        verified_percentage=verified_pct,
    )


class JSONLDReviewParser(html.parser.HTMLParser):
    """HTML parser looking for JSON-LD scripts containing Review objects."""

    def __init__(self) -> None:
        super().__init__()
        self.in_json_ld = False
        self.json_payloads: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() == "script":
            attr_dict = {k: v or "" for k, v in attrs}
            if attr_dict.get("type", "").lower() == "application/ld+json":
                self.in_json_ld = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.in_json_ld:
            self.in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self.in_json_ld and data.strip():
            self.json_payloads.append(data.strip())


def extract_reviews_from_json_ld(html_content: str) -> List[Review]:
    """Parse JSON-LD script blocks from HTML to find Schema.org Review elements.

    Args:
        html_content: Raw HTML text.

    Returns:
        List of extracted Review objects.
    """
    parser = JSONLDReviewParser()
    try:
        parser.feed(html_content)
    except (ValueError, TypeError, KeyError, AttributeError):
        pass

    reviews: List[Review] = []

    for payload_text in parser.json_payloads:
        try:
            data = json.loads(payload_text)
            review_nodes = _find_review_nodes(data)
            for idx, node in enumerate(review_nodes, 1):
                rev = _parse_single_json_ld_review(node, idx)
                if rev:
                    reviews.append(rev)
        except json.JSONDecodeError:
            continue

    return reviews


def _find_review_nodes(data: Any) -> List[Dict[str, Any]]:
    """Recursively search JSON-LD payload for Review nodes."""
    nodes = []
    if isinstance(data, dict):
        type_val = data.get("@type", "")
        is_review_type = type_val == "Review" or (
            isinstance(type_val, list) and "Review" in type_val
        )
        if is_review_type:
            nodes.append(data)
        if "review" in data:
            nodes.extend(_find_review_nodes(data["review"]))
        if "@graph" in data:
            nodes.extend(_find_review_nodes(data["@graph"]))
    elif isinstance(data, list):
        for item in data:
            nodes.extend(_find_review_nodes(item))
    return nodes


def _parse_single_json_ld_review(node: Dict[str, Any], idx: int) -> Optional[Review]:
    """Convert a Schema.org Review node into a Review dataclass instance."""
    author = "Anonymous"
    author_obj = node.get("author")
    if isinstance(author_obj, dict):
        author = author_obj.get("name", "Anonymous")
    elif isinstance(author_obj, str):
        author = author_obj

    rating = 5.0
    rating_obj = node.get("reviewRating")
    if isinstance(rating_obj, dict):
        val = rating_obj.get("ratingValue")
        if val is not None:
            try:
                rating = float(val)
            except ValueError:
                pass
    elif isinstance(rating_obj, (int, float)):
        rating = float(rating_obj)

    title = node.get("name") or node.get("headline") or ""
    raw_desc = node.get("reviewBody") or node.get("description") or ""
    text = clean_review_text(raw_desc)
    date = node.get("datePublished") or ""

    return Review(
        review_id=f"rev_{idx}",
        author=author,
        rating=rating,
        date=date,
        title=title,
        text=text,
        verified=True,
    )


def extract_reviews_fallback_html(html_content: str) -> List[Review]:
    """Fallback HTML card heuristic extractor for pages lacking JSON-LD.

    Args:
        html_content: Raw HTML content string.

    Returns:
        List of parsed Review instances.
    """
    reviews: List[Review] = []
    # Match review card blocks
    card_pat = (
        r"(<div[^>]*class=[\"'][^\"']*(?:review|comment)[^\"']*[\"'][^>]*>"
        r".*?</div>)"
    )
    blocks = re.findall(card_pat, html_content, re.IGNORECASE | re.DOTALL)

    for idx, block in enumerate(blocks, 1):
        # Rating extraction
        r_pat = r"(\d(?:\.\d)?)\s*(?:out of 5|stars|/5)"
        rating_match = re.search(r_pat, block, re.IGNORECASE)
        rating = float(rating_match.group(1)) if rating_match else 5.0

        # Author extraction
        a_pat = r"<[^>]*class=[\"'][^\"']*author[^\"']*[\"'][^>]*>(.*?)</[^>]+>"
        author_match = re.search(a_pat, block, re.IGNORECASE | re.DOTALL)
        if author_match:
            author = re.sub(r"<[^>]+>", "", author_match.group(1)).strip()
        else:
            author = "Anonymous"

        # Date extraction
        d_pat = r"\b(\d{4}-\d{2}-\d{2}|\b[A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b"
        date_match = re.search(d_pat, block)
        date = date_match.group(1) if date_match else ""

        # Verified status
        verified = bool(re.search(r"verified\s+purchase", block, re.IGNORECASE))

        # Review text
        t_pat = (
            r"<[^>]*class=[\"'][^\"']*(?:review-body|text|comment-body)"
            r"[^\"']*[\"'][^>]*>(.*?)</[^>]+>"
        )
        text_match = re.search(t_pat, block, re.IGNORECASE | re.DOTALL)
        raw_text = text_match.group(1) if text_match else block
        clean_text_val = clean_review_text(raw_text)

        if len(clean_text_val) > 10:
            reviews.append(
                Review(
                    review_id=f"rev_html_{idx}",
                    author=author,
                    rating=rating,
                    date=date,
                    title="",
                    text=clean_text_val[:500],
                    verified=verified,
                )
            )

    return reviews


def extract_product_reviews(html_content: str) -> List[Review]:
    """Extract product reviews using JSON-LD or HTML fallbacks.

    Args:
        html_content: Raw HTML text string.

    Returns:
        List of Review objects.
    """
    reviews = extract_reviews_from_json_ld(html_content)
    if not reviews:
        reviews = extract_reviews_fallback_html(html_content)
    return reviews


def export_to_csv(reviews: List[Review], filepath: str) -> None:
    """Export review items into CSV tabular format.

    Args:
        reviews: List of Review objects.
        filepath: Destination CSV file path.
    """
    fieldnames = [
        "review_id",
        "author",
        "rating",
        "date",
        "verified",
        "title",
        "text",
    ]
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in reviews:
            writer.writerow(r.to_dict())


def export_to_json(reviews: List[Review], stats: ReviewStats, filepath: str) -> None:
    """Export reviews and aggregated statistics to JSON file.

    Args:
        reviews: List of Review objects.
        stats: ReviewStats summary.
        filepath: Destination JSON file path.
    """
    payload = {
        "summary_statistics": stats.to_dict(),
        "reviews": [r.to_dict() for r in reviews],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Extract product reviews from HTML/JSON-LD pages for sentiment " + "analysis."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("source", type=str, help="URL or local HTML file path")
    parser.add_argument(
        "--format",
        choices=["csv", "json", "all"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument("--output", "-o", type=str, help="Output file path base")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Product Review Scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    html_content = ""
    if os.path.exists(parsed.source):
        with open(parsed.source, "r", encoding="utf-8") as f:
            html_content = f.read()
    else:
        headers = {"User-Agent": "Mozilla/5.0 ProductReviewScraper/1.0"}
        req = urllib.request.Request(parsed.source, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
                html_content = resp.read().decode("utf-8", errors="ignore")
        except (urllib.error.URLError, OSError, ValueError) as err:
            msg = f"Error loading source '{parsed.source}': {err}"
            print(msg, file=sys.stderr)
            return 1

    reviews = extract_product_reviews(html_content)
    stats = calculate_review_stats(reviews)

    msg = (
        f"Extracted {len(reviews)} reviews. Avg Rating: "
        f"{stats.average_rating}/5.0 (Verified: {stats.verified_percentage}%)"
    )
    print(msg)

    if parsed.output:
        base = parsed.output
        if parsed.format in ["csv", "all"]:
            csv_path = base if base.endswith(".csv") else f"{base}.csv"
            export_to_csv(reviews, csv_path)
            print(f"Reviews exported to {csv_path}")
        if parsed.format in ["json", "all"]:
            json_path = base if base.endswith(".json") else f"{base}.json"
            export_to_json(reviews, stats, json_path)
            print(f"Reviews and stats exported to {json_path}")
    else:
        if parsed.format == "csv":
            cols = [
                "review_id",
                "author",
                "rating",
                "date",
                "verified",
                "title",
                "text",
            ]
            writer = csv.DictWriter(sys.stdout, fieldnames=cols)
            writer.writeheader()
            for r in reviews:
                writer.writerow(r.to_dict())
        else:
            payload = {
                "summary_statistics": stats.to_dict(),
                "reviews": [r.to_dict() for r in reviews],
            }
            print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())

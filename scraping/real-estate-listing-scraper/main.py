"""Real Estate Listing Scraper and Extractor.

Scrapes property listings (price, location, bedrooms/bathrooms, sqft,
features) from HTML or JSON feeds, normalizes pricing, tags features, and
exports to CSV/JSON.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PropertyListing:
    """Represents a normalized real estate property listing."""

    title: str
    price: float
    currency: str = "USD"
    listing_type: str = "sale"  # sale or rent
    location: str = "Unknown"
    bedrooms: Optional[float] = None
    bathrooms: Optional[float] = None
    sqft: Optional[float] = None
    features: List[str] = field(default_factory=list)
    url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert listing object to dictionary."""
        data = asdict(self)
        data["features"] = ", ".join(self.features)
        return data


FEATURE_KEYWORDS = {
    "pool": ["pool", "swimming pool"],
    "garage": ["garage", "parking", "carport"],
    "fireplace": ["fireplace"],
    "balcony": ["balcony", "patio", "deck", "terrace"],
    "garden": ["garden", "yard", "backyard"],
    "waterfront": ["waterfront", "ocean view", "lakefront"],
    "elevator": ["elevator", "lift"],
    "air_conditioning": ["air conditioning", "ac", "central air"],
}


def normalize_price(price_str: str) -> Tuple[float, str, str]:
    """Parses and normalizes price strings.

    Returns: (numeric_price, currency, listing_type)
    Examples:
      "$1,250,000" -> (1250000.0, "USD", "sale")
      "$3,500/mo" -> (3500.0, "USD", "rent")
      "EUR 450k" -> (450000.0, "EUR", "sale")
    """
    if not price_str:
        return 0.0, "USD", "sale"

    raw = price_str.upper().strip()
    rent_keywords = ["/MO", "PER MONTH", "MONTHLY", "RENT"]
    is_rent = any(w in raw for w in rent_keywords)
    listing_type = "rent" if is_rent else "sale"

    currency = "USD"
    if "EUR" in raw or "€" in raw:
        currency = "EUR"
    elif "GBP" in raw or "£" in raw:
        currency = "GBP"
    elif "CAD" in raw or "C$" in raw:
        currency = "CAD"

    # Detect a K/M/B multiplier suffix attached to the number (e.g. "450K")
    # before stripping non-numeric characters like the "/MO" rent marker.
    multiplier = 1.0
    suffix_match = re.search(r"(?<=\d)\s?(K|M|B)(?![A-Z])", raw)
    if suffix_match:
        multiplier = {"K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}[
            suffix_match.group(1)
        ]
        raw = raw[: suffix_match.start()]

    clean = re.sub(r"[^\d\.]", "", raw)
    if not clean:
        return 0.0, currency, listing_type

    try:
        val = float(clean) * multiplier
    except ValueError:
        val = 0.0

    return val, currency, listing_type


def tag_features(text: str) -> List[str]:
    """Scan text for real estate features and return matching tags."""
    text_lower = text.lower()
    tags = []
    for tag, keywords in FEATURE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)
    return tags


class ListingHTMLParser(HTMLParser):
    """Parses HTML for json-ld or card element listings."""

    def __init__(self) -> None:
        super().__init__()
        self.in_script = False
        self.json_ld_blocks: List[str] = []
        self._current_data = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        if tag == "script" and attr_dict.get("type") == "application/ld+json":
            self.in_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_script:
            self.in_script = False
            if self._current_data.strip():
                self.json_ld_blocks.append(self._current_data.strip())
            self._current_data = ""

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self._current_data += data


def extract_listings_from_json(json_data: Any) -> List[PropertyListing]:
    """Extract PropertyListing objects from dict or list JSON data."""
    listings: List[PropertyListing] = []
    items = json_data if isinstance(json_data, list) else [json_data]

    for item in items:
        if not isinstance(item, dict):
            continue

        # JSON-LD or custom JSON format
        item_type = item.get("@type", "")
        valid_types = (
            "SingleFamilyResidence",
            "RealEstateListing",
            "Product",
            "Place",
            "",
        )
        if item_type in valid_types:
            raw_title = item.get("name") or item.get("title")
            title = str(raw_title or "Property Listing")
            price_raw = str(
                item.get("price") or item.get("offers", {}).get("price") or ""
            )
            price_val, currency, l_type = normalize_price(price_raw)

            loc = item.get("address") or item.get("location") or "Unknown"
            if isinstance(loc, dict):
                street = loc.get("streetAddress", "")
                locality = loc.get("addressLocality", "")
                loc = f"{street}, {locality}".strip(", ")

            beds = item.get("numberOfBedrooms") or item.get("bedrooms")
            baths = item.get("numberOfBathroomsTotal") or item.get("bathrooms")
            sqft = item.get("floorSize") or item.get("sqft")
            if isinstance(sqft, dict):
                sqft = sqft.get("value")

            desc = str(item.get("description", ""))
            features = tag_features(desc + " " + title)

            listing = PropertyListing(
                title=title,
                price=price_val,
                currency=currency,
                listing_type=l_type,
                location=str(loc) if loc else "Unknown",
                bedrooms=float(beds) if beds is not None else None,
                bathrooms=float(baths) if baths is not None else None,
                sqft=float(sqft) if sqft is not None else None,
                features=features,
                url=str(item.get("url", "")),
            )
            listings.append(listing)

    return listings


def parse_listings(content: str) -> List[PropertyListing]:
    """Parse listings from HTML or JSON string."""
    content_trimmed = content.strip()
    if content_trimmed.startswith(("{", "[")):
        try:
            data = json.loads(content_trimmed)
            return extract_listings_from_json(data)
        except json.JSONDecodeError:
            pass

    # HTML parsing for JSON-LD scripts
    parser = ListingHTMLParser()
    parser.feed(content)
    listings: List[PropertyListing] = []

    for block in parser.json_ld_blocks:
        try:
            data = json.loads(block)
            listings.extend(extract_listings_from_json(data))
        except json.JSONDecodeError:
            continue

    if not listings:
        # Regex heuristic fallback for HTML cards
        h_pat = r"<h[23][^>]*>(.*?)</h[23]>"
        p_pat = r"(\$\s?[\d,]+(?:\.\d+)?(?:\s?/mo|\s?k)?)"
        title_matches = re.findall(h_pat, content, re.IGNORECASE)
        price_matches = re.findall(p_pat, content, re.IGNORECASE)
        for idx in range(min(len(title_matches), len(price_matches))):
            price_val, curr, l_type = normalize_price(price_matches[idx])
            feats = tag_features(title_matches[idx])
            clean_title = re.sub(r"<[^>]+>", "", title_matches[idx]).strip()
            listings.append(
                PropertyListing(
                    title=clean_title,
                    price=price_val,
                    currency=curr,
                    listing_type=l_type,
                    features=feats,
                )
            )

    return listings


def filter_listings(
    listings: List[PropertyListing],
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_beds: Optional[float] = None,
    feature: Optional[str] = None,
) -> List[PropertyListing]:
    """Filter property listings based on pricing, beds, and feature tags."""
    res = listings
    if min_price is not None:
        res = [p for p in res if p.price >= min_price]
    if max_price is not None:
        res = [p for p in res if p.price <= max_price]
    if min_beds is not None:
        res = [p for p in res if p.bedrooms is not None and p.bedrooms >= min_beds]
    if feature:
        feat_lower = feature.lower()
        res = [p for p in res if any(feat_lower in f.lower() for f in p.features)]
    return res


def export_csv(listings: List[PropertyListing], filepath: str) -> None:
    """Export listings to CSV file."""
    if not listings:
        return
    fieldnames = list(listings[0].to_dict().keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in listings:
            writer.writerow(item.to_dict())


def export_json(listings: List[PropertyListing], filepath: str) -> None:
    """Export listings to JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump([item.to_dict() for item in listings], f, indent=2)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Scrape and extract real estate property listings."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--url", help="URL of real estate listings page")
    parser.add_argument("--file", help="Path to local file containing HTML/JSON")
    parser.add_argument("--min-price", type=float, help="Minimum price filter")
    parser.add_argument("--max-price", type=float, help="Maximum price filter")
    parser.add_argument("--min-beds", type=float, help="Minimum bedrooms filter")
    parser.add_argument(
        "--feature",
        help="Filter by required feature tag (e.g. pool, garage)",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Export format",
    )
    parser.add_argument("--output", help="Output filepath")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point for real-estate-listing-scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    content = ""
    if parsed.file:
        with open(parsed.file, "r", encoding="utf-8") as f:
            content = f.read()
    elif parsed.url:
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(parsed.url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:  # nosec B310
                content = resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError, ValueError) as err:
            print(f"Error fetching URL: {err}", file=sys.stderr)
            return 1
    else:
        print("Please provide --url or --file", file=sys.stderr)
        return 1

    listings = parse_listings(content)
    filtered = filter_listings(
        listings,
        min_price=parsed.min_price,
        max_price=parsed.max_price,
        min_beds=parsed.min_beds,
        feature=parsed.feature,
    )

    out_path = parsed.output or f"listings_output.{parsed.format}"
    if parsed.format == "csv":
        export_csv(filtered, out_path)
    else:
        export_json(filtered, out_path)

    msg = f"Extracted and saved {len(filtered)} property listings to {out_path}"
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())

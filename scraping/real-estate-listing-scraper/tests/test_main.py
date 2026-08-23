"""Unit tests for Real Estate Listing Scraper."""

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from typing import Any, List
from unittest.mock import MagicMock, patch

from main import (
    PropertyListing,
    build_parser,
    export_csv,
    export_json,
    filter_listings,
    main,
    normalize_price,
    parse_listings,
    tag_features,
)


def _urlopen_result(payload: str, status: int = 200) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = payload.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


class TestRealEstateListingScraper(unittest.TestCase):

    def test_normalize_price(self):
        val, curr, ltype = normalize_price("$1,250,000")
        self.assertEqual(val, 1250000.0)
        self.assertEqual(curr, "USD")
        self.assertEqual(ltype, "sale")

        val, curr, ltype = normalize_price("$3,500/mo")
        self.assertEqual(val, 3500.0)
        self.assertEqual(ltype, "rent")

        val, curr, ltype = normalize_price("EUR 450k")
        self.assertEqual(val, 450000.0)
        self.assertEqual(curr, "EUR")
        self.assertEqual(ltype, "sale")

    def test_tag_features(self):
        tags = tag_features(
            "Luxury villa with a swimming pool, private garage, and balcony"
        )
        self.assertIn("pool", tags)
        self.assertIn("garage", tags)
        self.assertIn("balcony", tags)

    def test_parse_json_listings(self):
        json_data = """
        [
            {
                "@type": "SingleFamilyResidence",
                "name": "Sunset Modern Villa",
                "price": "$2,500,000",
                "address": {
                    "streetAddress": "123 Ocean Drive",
                    "addressLocality": "Miami"
                },
                "numberOfBedrooms": 4,
                "numberOfBathroomsTotal": 3.5,
                "floorSize": {"value": 3200},
                "description": "Beautiful waterfront house with pool and garage"
            }
        ]
        """
        listings = parse_listings(json_data)
        self.assertEqual(len(listings), 1)
        item = listings[0]
        self.assertEqual(item.title, "Sunset Modern Villa")
        self.assertEqual(item.price, 2500000.0)
        self.assertEqual(item.bedrooms, 4.0)
        self.assertIn("pool", item.features)
        self.assertIn("waterfront", item.features)

    def test_filter_listings(self):
        p1 = PropertyListing("P1", price=500000, bedrooms=2, features=["pool"])
        p2 = PropertyListing("P2", price=1200000, bedrooms=4, features=["garage"])
        listings = [p1, p2]

        filtered = filter_listings(listings, min_price=600000)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].title, "P2")

        filtered_feat = filter_listings(listings, feature="pool")
        self.assertEqual(len(filtered_feat), 1)
        self.assertEqual(filtered_feat[0].title, "P1")

    def test_exports(self):
        p = PropertyListing("Test Home", price=300000, bedrooms=3, features=["garage"])
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "out.csv")
            json_path = os.path.join(tmpdir, "out.json")

            export_csv([p], csv_path)
            self.assertTrue(os.path.exists(csv_path))

            export_json([p], json_path)
            self.assertTrue(os.path.exists(json_path))


class TestNormalizePriceVariants(unittest.TestCase):
    """Price normalisation across currencies, rent markers and multipliers."""

    def test_empty_price_returns_zeroed_sale_usd(self) -> None:
        self.assertEqual(normalize_price(""), (0.0, "USD", "sale"))
        self.assertEqual(normalize_price("   "), (0.0, "USD", "sale"))

    def test_currency_symbols_and_codes(self) -> None:
        self.assertEqual(normalize_price("£275,000")[1], "GBP")
        self.assertEqual(normalize_price("GBP 275000")[1], "GBP")
        self.assertEqual(normalize_price("C$ 480,000")[1], "CAD")
        self.assertEqual(normalize_price("$480,000")[1], "USD")

    def test_rent_markers_besides_slash_mo(self) -> None:
        self.assertEqual(normalize_price("1,800 per month")[2], "rent")
        self.assertEqual(normalize_price("Monthly rent $900")[2], "rent")
        self.assertEqual(normalize_price("$2,150 /mo")[2], "rent")

    def test_kmb_multipliers(self) -> None:
        self.assertEqual(normalize_price("EUR 450k"), (450000.0, "EUR", "sale"))
        self.assertEqual(normalize_price("$2.5M"), (2500000.0, "USD", "sale"))
        self.assertEqual(normalize_price("£1.2b")[0], 1200000000.0)

    def test_non_numeric_price_yields_zero(self) -> None:
        self.assertEqual(normalize_price("Contact agent"), (0.0, "USD", "sale"))
        self.assertEqual(normalize_price("$1.2.3")[0], 0.0)


class TestTagFeatures(unittest.TestCase):
    """Feature keyword tagging."""

    def test_all_feature_groups_are_detected(self) -> None:
        text = (
            "Home with swimming pool, garage parking, fireplace, balcony, "
            "garden yard, waterfront views, elevator and central air "
            "conditioning"
        )
        tags = tag_features(text)
        self.assertEqual(
            sorted(tags),
            sorted(
                [
                    "pool",
                    "garage",
                    "fireplace",
                    "balcony",
                    "garden",
                    "waterfront",
                    "elevator",
                    "air_conditioning",
                ]
            ),
        )

    def test_no_features_yields_empty_list(self) -> None:
        self.assertEqual(tag_features("A plain studio apartment"), [])


class TestParseListings(unittest.TestCase):
    """JSON, JSON-LD-in-HTML and regex card parsing."""

    def test_non_dict_items_are_skipped(self) -> None:
        raw = json.dumps(
            [
                {"@type": "Product", "name": "Loft", "price": "$300k"},
                "not-a-dict",
                42,
            ]
        )
        listings = parse_listings(raw)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].title, "Loft")
        self.assertEqual(listings[0].price, 300000.0)

    def test_unknown_type_items_are_skipped(self) -> None:
        raw = json.dumps([{"@type": "Car", "name": "Nope"}])
        self.assertEqual(parse_listings(raw), [])

    def test_json_ld_script_inside_html_is_extracted(self) -> None:
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "RealEstateListing", "name": "Hillside Condo",
         "offers": {"price": "$410,000"},
         "address": {"streetAddress": "9 Elm St", "addressLocality": "Austin"},
         "numberOfBedrooms": 2, "bathrooms": 2,
         "floorSize": {"value": 1100},
         "description": "Balcony with elevator access"}
        </script>
        </head><body><p>Listing page</p></body></html>
        """
        listings = parse_listings(html)
        self.assertEqual(len(listings), 1)
        item = listings[0]
        self.assertEqual(item.title, "Hillside Condo")
        self.assertEqual(item.price, 410000.0)
        self.assertEqual(item.location, "9 Elm St, Austin")
        self.assertEqual(item.bedrooms, 2.0)
        self.assertEqual(item.bathrooms, 2.0)
        self.assertEqual(item.sqft, 1100.0)
        self.assertIn("balcony", item.features)
        self.assertIn("elevator", item.features)

    def test_malformed_json_ld_blocks_are_skipped(self) -> None:
        html = (
            "<script type='application/ld+json'>{broken!!}</script>"
            "<h2>Cottage with garden</h2><p>$250,000</p>"
        )
        listings = parse_listings(html)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].title, "Cottage with garden")

    def test_regex_card_fallback_pairs_titles_with_prices(self) -> None:
        html = """
        <div class="results">
            <h3>Charming Bungalow with Pool</h3><span>$650,000</span>
            <h3>City Apartment</h3><span>$2,400/mo</span>
        </div>
        """
        listings = parse_listings(html)
        self.assertEqual(len(listings), 2)
        first = listings[0]
        self.assertEqual(first.title, "Charming Bungalow with Pool")
        self.assertEqual(first.price, 650000.0)
        self.assertIn("pool", first.features)
        second = listings[1]
        self.assertEqual(second.listing_type, "rent")
        self.assertEqual(second.price, 2400.0)

    def test_invalid_json_root_falls_through_to_html_parsing(self) -> None:
        content = "{definitely not valid json"
        self.assertEqual(parse_listings(content), [])


class TestFilterListings(unittest.TestCase):
    """Filter combinations over parsed listings."""

    def _listings(self) -> List[PropertyListing]:
        return [
            PropertyListing(
                "Cheap Studio", price=200000, bedrooms=None, features=["pool"]
            ),
            PropertyListing(
                "Family Home", price=800000, bedrooms=4, features=["Garage"]
            ),
            PropertyListing(
                "Mid Condo", price=500000, bedrooms=2, features=["balcony", "pool"]
            ),
        ]

    def test_max_price_filter(self) -> None:
        filtered = filter_listings(self._listings(), max_price=500000)
        self.assertEqual([p.title for p in filtered], ["Cheap Studio", "Mid Condo"])

    def test_min_beds_excludes_unknown_bedroom_counts(self) -> None:
        filtered = filter_listings(self._listings(), min_beds=2)
        self.assertEqual([p.title for p in filtered], ["Family Home", "Mid Condo"])

    def test_feature_filter_is_case_insensitive_substring(self) -> None:
        filtered = filter_listings(self._listings(), feature="GARAGE")
        self.assertEqual([p.title for p in filtered], ["Family Home"])


class TestExports(unittest.TestCase):
    """Exporter edge cases including empty input."""

    def test_export_csv_skips_writing_when_no_listings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.csv")
            export_csv([], path)
            self.assertFalse(os.path.exists(path))

    def test_to_dict_joins_features_into_single_field(self) -> None:
        listing = PropertyListing("A", price=1, features=["pool", "garage"])
        as_dict: Any = listing.to_dict()
        self.assertEqual(as_dict["features"], "pool, garage")


class TestRealEstateCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    SAMPLE_JSON = json.dumps(
        [
            {
                "@type": "SingleFamilyResidence",
                "name": "CLI Villa",
                "price": "$700,000",
                "numberOfBedrooms": 3,
            },
            {
                "@type": "Apartment",
                "name": "Filtered Out",
                "price": "$100,000",
            },
        ]
    )

    def test_build_parser_defaults(self) -> None:
        args = build_parser().parse_args(["--url", "https://re.example.com"])
        self.assertIsNone(args.min_price)
        self.assertIsNone(args.feature)
        self.assertEqual(args.format, "csv")
        self.assertIsNone(args.output)

    def _run_main(self, argv: List[str]) -> tuple:
        """Run main() capturing stdout/stderr; return (code, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_main_requires_source(self) -> None:
        code, _, err = self._run_main([])
        self.assertEqual(code, 1)
        self.assertIn("Please provide --url or --file", err)

    def test_main_reads_file_applies_filters_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "feed.json")
            out_path = os.path.join(tmpdir, "listings.json")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(self.SAMPLE_JSON)
            argv = [
                "--file",
                src_path,
                "--min-price",
                "500000",
                "--min-beds",
                "2",
                "--format",
                "json",
                "--output",
                out_path,
            ]
            code, out, _ = self._run_main(argv)
            self.assertEqual(code, 0)
            self.assertIn(f"Extracted and saved 1 property listings to {out_path}", out)
            with open(out_path, encoding="utf-8") as f:
                saved: Any = json.load(f)
            self.assertEqual(saved[0]["title"], "CLI Villa")

    def test_main_fetches_url_and_defaults_to_csv_output(self) -> None:
        default_path = "listings_output.csv"
        try:
            with patch(
                "main.urllib.request.urlopen",
                return_value=_urlopen_result(self.SAMPLE_JSON),
            ):
                code, out, _ = self._run_main(
                    ["--url", "https://realestate.example.com/list"]
                )
            self.assertEqual(code, 0)
            self.assertIn(
                f"Extracted and saved 1 property listings to {default_path}", out
            )
        finally:
            if os.path.exists(default_path):
                os.remove(default_path)

    def test_main_url_error_returns_exit_code_one(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("no route to host"),
        ):
            code, _, err = self._run_main(["--url", "https://re.example.com/x"])
        self.assertEqual(code, 1)
        self.assertIn("Error fetching URL:", err)


if __name__ == "__main__":
    unittest.main()

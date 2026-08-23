"""Unit tests for Product Review Scraper."""

import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
import urllib.error
from typing import Any, List
from unittest.mock import MagicMock, patch

from main import (
    Review,
    ReviewStats,
    build_parser,
    calculate_review_stats,
    clean_review_text,
    export_to_csv,
    export_to_json,
    extract_product_reviews,
    extract_reviews_fallback_html,
    extract_reviews_from_json_ld,
    main,
)


def _urlopen_result(payload: str, status: int = 200) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = payload.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


class TestProductReviewScraper(unittest.TestCase):
    """Test suite for review text cleaning, stats calculation, and JSON-LD
    parsing."""

    def test_clean_review_text(self) -> None:
        raw_text = (
            "  <p>Great product! &quot;Highly recommended&quot;</p>\n\n  Works well.  "
        )
        cleaned = clean_review_text(raw_text)
        self.assertEqual(cleaned, 'Great product! "Highly recommended" Works well.')

    def test_calculate_review_stats(self) -> None:
        reviews = [
            Review("1", "Alice", 5.0, "2026-01-01", "Great", "Excellent product", True),
            Review("2", "Bob", 4.0, "2026-01-02", "Good", "Pretty good overall", True),
            Review("3", "Charlie", 2.0, "2026-01-03", "Poor", "Broke easily", False),
        ]
        stats = calculate_review_stats(reviews)
        self.assertEqual(stats.total_reviews, 3)
        self.assertEqual(stats.average_rating, 3.67)
        self.assertEqual(stats.rating_distribution[5], 1)
        self.assertEqual(stats.rating_distribution[4], 1)
        self.assertEqual(stats.rating_distribution[2], 1)
        self.assertEqual(stats.verified_count, 2)
        self.assertEqual(stats.verified_percentage, 66.7)

    def test_extract_reviews_from_json_ld(self) -> None:
        html = """
        <html>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Wireless Headphones",
            "review": [
                {
                    "@type": "Review",
                    "author": {"@type": "Person", "name": "Jane Doe"},
                    "reviewRating": {"@type": "Rating", "ratingValue": "5"},
                    "name": "Amazing Sound",
                    "reviewBody": "Best noise cancelling headphones ever!",
                    "datePublished": "2026-05-15"
                }
            ]
        }
        </script>
        </html>
        """
        reviews = extract_reviews_from_json_ld(html)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].author, "Jane Doe")
        self.assertEqual(reviews[0].rating, 5.0)
        self.assertEqual(reviews[0].title, "Amazing Sound")
        self.assertEqual(reviews[0].text, "Best noise cancelling headphones ever!")

    def test_extract_product_reviews_fallback(self) -> None:
        html = """
        <html>
        <body>
            <div class="review-card">
                <span class="rating">4.5 out of 5 stars</span>
                <span class="author">John Smith</span>
                <span class="verified-purchase">Verified Purchase</span>
                <p class="review-body">Solid build quality and great battery life.</p>
            </div>
        </body>
        </html>
        """
        reviews = extract_product_reviews(html)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].rating, 4.5)
        self.assertEqual(reviews[0].author, "John Smith")
        self.assertTrue(reviews[0].verified)
        self.assertIn("Solid build quality", reviews[0].text)


class TestReviewTextCleaning(unittest.TestCase):
    """clean_review_text normalisation behaviour."""

    def test_empty_and_whitespace_only_text_becomes_empty(self) -> None:
        self.assertEqual(clean_review_text(""), "")
        self.assertEqual(clean_review_text("   \n\t "), "")

    def test_html_entities_and_tags_are_normalised(self) -> None:
        cleaned = clean_review_text("<b>Broke</b> after &lt;2&gt; days &amp; weeks")
        self.assertEqual(cleaned, "Broke after <2> days & weeks")


class TestCalculateReviewStats(unittest.TestCase):
    """Aggregation statistics edge cases."""

    def test_empty_review_list_yields_zeroed_stats(self) -> None:
        stats = calculate_review_stats([])
        self.assertIsInstance(stats, ReviewStats)
        self.assertEqual(stats.total_reviews, 0)
        self.assertEqual(stats.average_rating, 0.0)
        self.assertEqual(stats.rating_distribution, {1: 0, 2: 0, 3: 0, 4: 0, 5: 0})
        self.assertEqual(stats.verified_percentage, 0.0)

    def test_ratings_are_clamped_into_distribution_buckets(self) -> None:
        reviews = [
            Review("1", "A", 4.6, "2026-01-01", "", "Great", False),
            Review("2", "B", 0.4, "2026-01-02", "", "Awful", True),
            Review("3", "C", 3.5, "2026-01-03", "", "Ok", True),
        ]
        stats = calculate_review_stats(reviews)
        self.assertEqual(stats.rating_distribution[5], 1)
        self.assertEqual(stats.rating_distribution[1], 1)
        self.assertEqual(stats.rating_distribution[4], 1)
        self.assertEqual(stats.average_rating, 2.83)

    def test_to_dict_shapes(self) -> None:
        review = Review("1", "A", 5.0, "2026-01-01", "T", "Body text", True).to_dict()
        self.assertEqual(
            set(review.keys()),
            {
                "review_id",
                "author",
                "rating",
                "date",
                "title",
                "text",
                "verified",
            },
        )
        stats = calculate_review_stats([Review("1", "A", 5.0, "d", "", "b", True)])
        stats_dict = stats.to_dict()
        self.assertEqual(stats_dict["verified_count"], 1)
        self.assertEqual(stats_dict["verified_percentage"], 100.0)


class TestJsonLdParsingVariants(unittest.TestCase):
    """JSON-LD extraction covering recursive search and field fallbacks."""

    def test_malformed_json_payload_is_skipped(self) -> None:
        html = "<script type='application/ld+json'>{definitely not json}</script>"
        self.assertEqual(extract_reviews_from_json_ld(html), [])

    def test_unparseable_input_returns_empty_list(self) -> None:
        self.assertEqual(extract_reviews_from_json_ld(None), [])

    def test_graph_wrapper_and_type_list_are_supported(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@graph": [
            {"@type": ["Review", "SocialMediaPosting"],
             "author": "Plain String Author",
             "reviewRating": 4,
             "headline": "List-typed node",
             "description": "Found inside @graph."}
        ]}
        </script>
        """
        reviews = extract_reviews_from_json_ld(html)
        self.assertEqual(len(reviews), 1)
        rev = reviews[0]
        self.assertEqual(rev.author, "Plain String Author")
        self.assertEqual(rev.rating, 4.0)
        self.assertEqual(rev.title, "List-typed node")
        self.assertEqual(rev.text, "Found inside @graph.")
        self.assertTrue(rev.verified)

    def test_invalid_rating_value_keeps_default_of_five(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@type": "Review",
         "reviewRating": {"ratingValue": "excellent"},
         "reviewBody": "No numeric rating present here."}
        </script>
        """
        reviews = extract_reviews_from_json_ld(html)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].rating, 5.0)
        self.assertEqual(reviews[0].author, "Anonymous")

    def test_review_body_falls_back_to_description(self) -> None:
        html = (
            '<script type="application/ld+json">{"@type": "Review", '
            '"name": "Headline wins", '
            '"description": "Description body used when no reviewBody."}'
            "</script>"
        )
        reviews = extract_reviews_from_json_ld(html)
        self.assertEqual(reviews[0].title, "Headline wins")
        self.assertEqual(reviews[0].text, "Description body used when no reviewBody.")


class TestFallbackHtmlExtraction(unittest.TestCase):
    """Regex card heuristic extractor for pages without JSON-LD."""

    def test_missing_author_defaults_to_anonymous(self) -> None:
        html = """
        <div class="review">
            <span>4 out of 5</span>
            <span class="date">2026-02-02</span>
            <p class="review-body">This is a long enough body text.</p>
        </div>
        """
        reviews = extract_reviews_fallback_html(html)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].author, "Anonymous")
        self.assertFalse(reviews[0].verified)
        self.assertEqual(reviews[0].date, "2026-02-02")
        self.assertEqual(reviews[0].rating, 4.0)

    def test_short_or_empty_blocks_are_discarded(self) -> None:
        html = "<div class='comment'>tiny</div><div class='review'></div>"
        self.assertEqual(extract_product_reviews(html), [])


class TestExporters(unittest.TestCase):
    """CSV and JSON exporters write parseable files."""

    def setUp(self) -> None:
        self.reviews: List[Review] = [
            Review("r1", "Alice", 5.0, "2026-01-01", "Love it", "Great value", True),
            Review("r2", "Bob", 2.0, "2026-01-02", "Meh", "Stopped working", False),
        ]
        self.stats = calculate_review_stats(self.reviews)

    def test_export_to_csv_writes_header_and_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "reviews.csv")
            export_to_csv(self.reviews, path)
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["author"], "Alice")
        self.assertEqual(rows[0]["verified"], "True")
        self.assertEqual(rows[1]["rating"], "2.0")

    def test_export_to_json_includes_summary_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "reviews.json")
            export_to_json(self.reviews, self.stats, path)
            with open(path, encoding="utf-8") as f:
                payload: Any = json.load(f)
        self.assertEqual(payload["summary_statistics"]["total_reviews"], 2)
        self.assertEqual(payload["summary_statistics"]["average_rating"], 3.5)
        self.assertEqual(payload["reviews"][1]["review_id"], "r2")


class TestProductReviewCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    SAMPLE_HTML = """
    <html><body>
    <script type="application/ld+json">
    {"@type": "Review", "author": {"name": "Dana"},
     "reviewRating": {"ratingValue": 5},
     "reviewBody": "Superb keyboard feel and battery life.",
     "datePublished": "2026-03-03"}
    </script>
    </body></html>
    """

    def test_build_parser_defaults(self) -> None:
        args = build_parser().parse_args(["some-source"])
        self.assertEqual(args.format, "json")
        self.assertIsNone(args.output)

    def _run_main(self, argv: List[str]) -> tuple:
        """Run main() capturing stdout/stderr; return (code, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_main_reads_local_file_and_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "page.html")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(self.SAMPLE_HTML)
            code, out, _ = self._run_main([src_path])
        self.assertEqual(code, 0)
        self.assertIn("Extracted 1 reviews.", out)
        json_start = out.index("{")
        payload: Any = json.loads(out[json_start:])
        self.assertEqual(payload["summary_statistics"]["average_rating"], 5.0)
        self.assertEqual(payload["reviews"][0]["author"], "Dana")

    def test_main_csv_stdout_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "page.html")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(self.SAMPLE_HTML)
            code, out, _ = self._run_main([src_path, "--format", "csv"])
        self.assertEqual(code, 0)
        csv_start = next(
            i for i, line in enumerate(out.splitlines()) if line.startswith("review_id")
        )
        rows = list(
            csv.DictReader(io.StringIO("\n".join(out.splitlines()[csv_start:])))
        )
        self.assertEqual(rows[0]["review_id"], "rev_1")

    def test_main_url_source_and_dual_export_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = os.path.join(tmpdir, "export")
            argv = [
                "https://shop.example.com/product/1",
                "--format",
                "all",
                "--output",
                base,
            ]
            with patch(
                "main.urllib.request.urlopen",
                return_value=_urlopen_result(self.SAMPLE_HTML),
            ):
                code, out, _ = self._run_main(argv)
            self.assertEqual(code, 0)
            self.assertIn(f"Reviews exported to {base}.csv", out)
            self.assertIn(f"Reviews and stats exported to {base}.json", out)
            self.assertTrue(os.path.exists(f"{base}.csv"))
            self.assertTrue(os.path.exists(f"{base}.json"))

    def test_main_unreachable_url_returns_exit_code_one(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection reset"),
        ):
            code, _, err = self._run_main(["https://shop.example.com/x"])
        self.assertEqual(code, 1)
        self.assertIn("Error loading source", err)


if __name__ == "__main__":
    unittest.main()

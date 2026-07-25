"""Unit tests for Product Review Scraper."""

import unittest

from main import (
    Review,
    calculate_review_stats,
    clean_review_text,
    extract_product_reviews,
    extract_reviews_from_json_ld,
)


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


if __name__ == "__main__":
    unittest.main()

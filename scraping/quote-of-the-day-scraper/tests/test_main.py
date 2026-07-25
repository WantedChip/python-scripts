import os
import tempfile
import unittest

from main import append_quote_to_file, format_quote_markdown, is_quote_duplicate


class TestQuoteOfTheDayScraper(unittest.TestCase):
    """Unit tests for Quote of the Day Scraper."""

    def test_format_quote_markdown(self):
        md = format_quote_markdown(
            "Life is simple.", "Anonymous", category="Philosophy"
        )
        self.assertIn('> "Life is simple."', md)
        self.assertIn("> — **Anonymous**", md)
        self.assertIn("Category: Philosophy", md)
        self.assertIn("---", md)

    def test_is_quote_duplicate(self):
        existing = (
            '> "The best way to predict the future is to create it."\n'
            "> — **Peter Drucker**"
        )
        self.assertTrue(
            is_quote_duplicate(
                existing, "The best way to predict the future is to create it."
            )
        )
        self.assertFalse(is_quote_duplicate(existing, "Knowledge is power."))

    def test_append_quote_to_file_and_deduplicate(self):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".md") as tmp:
            tmp_path = tmp.name

        try:
            # First append should succeed
            res1 = append_quote_to_file(
                tmp_path, "Stay hungry, stay foolish.", "Steve Jobs"
            )
            self.assertTrue(res1)

            # Duplicate append should be rejected
            res2 = append_quote_to_file(
                tmp_path, "Stay hungry, stay foolish.", "Steve Jobs"
            )
            self.assertFalse(res2)

            # Force append should succeed
            res3 = append_quote_to_file(
                tmp_path,
                "Stay hungry, stay foolish.",
                "Steve Jobs",
                force=True,
            )
            self.assertTrue(res3)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()

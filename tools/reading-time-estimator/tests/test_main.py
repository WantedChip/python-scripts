"""Unit tests for Reading Time Estimator."""

import unittest

from main import clean_html, count_words, estimate_reading_time


class TestReadingTimeEstimator(unittest.TestCase):
    """Test suite for reading time estimation and text extraction."""

    def test_word_count(self):
        text = "The quick brown fox jumps over the lazy dog."
        self.assertEqual(count_words(text), 9)

    def test_empty_word_count(self):
        self.assertEqual(count_words(""), 0)
        self.assertEqual(count_words("   \n\t  "), 0)

    def test_clean_html_extraction(self):
        html = "<html><body><h1>Title</h1><p>Hello <b>world</b>!</p></body></html>"
        extracted = clean_html(html)
        self.assertIn("Title", extracted)
        self.assertIn("Hello world", extracted)
        self.assertNotIn("<html>", extracted)

    def test_clean_html_with_script(self):
        html = "<p>Visible text</p><script>console.log('ignore me');</script>"
        extracted = clean_html(html)
        self.assertIn("Visible text", extracted)
        self.assertNotIn("ignore me", extracted)

    def test_reading_time_calculation(self):
        # 200 words at 200 wpm = 1 min (60 seconds)
        text = "word " * 200
        result = estimate_reading_time(text, wpm=200)
        self.assertEqual(result["word_count"], 200)
        self.assertEqual(result["minutes"], 1)
        self.assertEqual(result["seconds"], 0)
        self.assertEqual(result["formatted"], "1 min")

    def test_reading_time_short_text(self):
        # 50 words at 200 wpm = 15 seconds
        text = "word " * 50
        result = estimate_reading_time(text, wpm=200)
        self.assertEqual(result["minutes"], 0)
        self.assertEqual(result["seconds"], 15)
        self.assertEqual(result["formatted"], "15 sec")

    def test_invalid_wpm(self):
        with self.assertRaises(ValueError):
            estimate_reading_time("sample text", wpm=0)


if __name__ == "__main__":
    unittest.main()

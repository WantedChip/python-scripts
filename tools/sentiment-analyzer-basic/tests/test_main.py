"""Unit tests for Basic Sentiment Analyzer."""

import unittest

from main import analyze_sentiment, tokenize


class TestSentimentAnalyzer(unittest.TestCase):
    """Test suite for sentiment analysis functions."""

    def test_tokenize(self):
        text = "Hello world! This is great, isn't it?"
        tokens = tokenize(text)
        self.assertIn("hello", tokens)
        self.assertIn("isn't", tokens)

    def test_positive_sentiment(self):
        text = "This product is amazing and fantastic, I love it!"
        res = analyze_sentiment(text)
        self.assertEqual(res["overall_sentiment"], "Positive")
        self.assertGreater(res["net_score"], 0)
        self.assertIn("amazing", res["matched_positive"])

    def test_negative_sentiment(self):
        text = "The service was terrible, slow, and worst experience ever."
        res = analyze_sentiment(text)
        self.assertEqual(res["overall_sentiment"], "Negative")
        self.assertLess(res["net_score"], 0)
        self.assertIn("terrible", res["matched_negative"])

    def test_negation_handling(self):
        text = "The movie was not good and not pleasant."
        res = analyze_sentiment(text)
        self.assertEqual(res["overall_sentiment"], "Negative")
        self.assertIn("not good", res["matched_negative"])

    def test_negated_negative_word(self):
        text = "It was not terrible."
        res = analyze_sentiment(text)
        self.assertIn("not terrible", res["matched_positive"])

    def test_neutral_sentiment(self):
        text = "The table is made of wood and stands in the center."
        res = analyze_sentiment(text)
        self.assertEqual(res["overall_sentiment"], "Neutral")
        self.assertEqual(res["net_score"], 0)


if __name__ == "__main__":
    unittest.main()

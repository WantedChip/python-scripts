"""Unit tests for Keyword Extractor."""

import unittest

from main import build_ngrams, extract_keywords_tf, extract_keywords_tfidf, tokenize


class TestKeywordExtractor(unittest.TestCase):
    """Test suite for tokenization, n-grams, and keyword extraction."""

    def test_tokenize(self):
        text = "Machine learning algorithms learn patterns from data."
        tokens = tokenize(text)
        self.assertIn("machine", tokens)
        self.assertIn("learning", tokens)

    def test_build_ngrams(self):
        tokens = ["artificial", "intelligence", "machine", "learning"]
        bigrams = build_ngrams(tokens, n=2)
        self.assertEqual(bigrams[0], "artificial intelligence")
        self.assertEqual(bigrams[1], "intelligence machine")
        self.assertEqual(len(bigrams), 3)

    def test_extract_keywords_tf(self):
        text = "Python Python Python code code data data data data test"
        keywords = extract_keywords_tf(text, ngram_size=1, top_n=2)
        self.assertEqual(len(keywords), 2)
        self.assertEqual(keywords[0][0], "data")
        self.assertEqual(keywords[1][0], "python")

    def test_extract_keywords_tfidf(self):
        docs = [
            "quantum computing quantum physics quantum mechanics",
            "cooking recipes baking cakes kitchen food",
            "sports football basketball soccer games",
        ]
        keywords = extract_keywords_tfidf(docs, target_index=0, top_n=2)
        self.assertTrue(any(kw[0] == "quantum" for kw in keywords))

    def test_empty_text_handling(self):
        self.assertEqual(extract_keywords_tf("", top_n=5), [])


if __name__ == "__main__":
    unittest.main()

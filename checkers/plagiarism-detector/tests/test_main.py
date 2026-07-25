"""Unit tests for Plagiarism Detector."""

import unittest

from main import (
    analyze_plagiarism,
    calculate_cosine_similarity,
    calculate_jaccard_similarity,
    find_matching_snippets,
    generate_ngrams,
    tokenize,
)


class TestPlagiarismDetector(unittest.TestCase):
    """Test suite for similarity algorithms and snippet extraction."""

    def test_tokenize(self):
        text = "Plagiarism detection tool detects overlapping words."
        tokens = tokenize(text)
        self.assertEqual(tokens[0], "plagiarism")
        self.assertEqual(len(tokens), 6)

    def test_generate_ngrams(self):
        words = ["the", "quick", "brown", "fox", "jumps"]
        ngrams = generate_ngrams(words, n=3)
        self.assertEqual(len(ngrams), 3)
        self.assertEqual(ngrams[0], ("the", "quick", "brown"))

    def test_cosine_similarity_identical(self):
        words = ["apple", "banana", "cherry"]
        sim = calculate_cosine_similarity(words, words)
        self.assertAlmostEqual(sim, 1.0)

    def test_cosine_similarity_different(self):
        w1 = ["apple", "banana"]
        w2 = ["dog", "cat"]
        sim = calculate_cosine_similarity(w1, w2)
        self.assertEqual(sim, 0.0)

    def test_jaccard_similarity(self):
        s1 = {("a", "b"), ("b", "c")}
        s2 = {("a", "b"), ("c", "d")}
        jaccard = calculate_jaccard_similarity(s1, s2)
        self.assertAlmostEqual(jaccard, 1 / 3)

    def test_find_matching_snippets(self):
        w1 = ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
        w2 = ["a", "quick", "brown", "fox", "runs", "fast"]
        snippets = find_matching_snippets(w1, w2, min_length=3)
        self.assertIn("quick brown fox", snippets)

    def test_analyze_plagiarism_high_similarity(self):
        text1 = (
            "Natural language processing allows computers "
            "to understand text accurately."
        )
        text2 = (
            "Natural language processing enables computers "
            "to comprehend text accurately."
        )
        report = analyze_plagiarism(text1, text2, ngram_size=2)
        self.assertGreater(report["similarity_percentage"], 50.0)


if __name__ == "__main__":
    unittest.main()

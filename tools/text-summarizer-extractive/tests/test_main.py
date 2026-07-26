import unittest

from main import calculate_word_frequencies, split_sentences, summarize


class TestTextSummarizerExtractive(unittest.TestCase):
    """Test suite for extractive summarization logic."""

    def test_split_sentences(self):
        text = "First sentence. Second sentence! Is this third sentence?"
        sentences = split_sentences(text)
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences[0], "First sentence.")

    def test_calculate_word_frequencies(self):
        text = "Python is great. Python programming is awesome."
        freqs = calculate_word_frequencies(text)
        self.assertIn("python", freqs)
        self.assertEqual(freqs["python"], 1.0)

    def test_summarize_ratio(self):
        sentences = [f"Sentence number {i} with unique content." for i in range(10)]
        text = " ".join(sentences)
        summary = summarize(text, ratio=0.3)
        summary_sentences = split_sentences(summary)
        self.assertLessEqual(len(summary_sentences), 4)

    def test_summarize_count(self):
        sentences = [
            "Artificial intelligence is transforming modern technology rapidly.",
            "Machine learning models process massive data sets every day.",
            "Weather forecasts predict rain in tomorrow's morning schedule.",
            "AI technology continues to expand across various global industries.",
        ]
        text = " ".join(sentences)
        summary = summarize(text, num_sentences=2)
        summary_sentences = split_sentences(summary)
        self.assertEqual(len(summary_sentences), 2)

    def test_empty_text(self):
        self.assertEqual(summarize(""), "")


if __name__ == "__main__":
    unittest.main()

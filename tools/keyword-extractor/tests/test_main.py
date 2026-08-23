"""Unit tests for Keyword Extractor."""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from main import (
    build_ngrams,
    build_parser,
    extract_keywords_tf,
    extract_keywords_tfidf,
    is_valid_ngram,
    main,
    tokenize,
)


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


class TestNgramHelpers(unittest.TestCase):
    """Test suite for n-gram construction and stop-word boundary checks."""

    def test_build_ngrams_single_returns_words_unchanged(self) -> None:
        """n=1 (or less) must return the token list itself."""
        tokens = ["alpha", "beta", "gamma"]
        self.assertEqual(build_ngrams(tokens, n=1), tokens)
        self.assertEqual(build_ngrams(tokens, n=0), tokens)

    def test_is_valid_ngram_boundaries(self) -> None:
        """Phrases starting or ending with a stop word are invalid."""
        self.assertTrue(is_valid_ngram("machine learning", {"the"}))
        self.assertFalse(is_valid_ngram("the learning", {"the"}))
        self.assertFalse(is_valid_ngram("machine the", {"the"}))

    def test_extract_keywords_tf_bigrams_filters_stop_edges(self) -> None:
        """TF mode with bigrams keeps only phrases without stop-word edges."""
        text = "Machine learning models love data. The data drives machine learning."
        keywords = extract_keywords_tf(text, ngram_size=2, top_n=3)
        self.assertTrue(len(keywords) > 0)
        for kw, score in keywords:
            parts = kw.split()
            self.assertEqual(len(parts), 2)
            self.assertGreater(score, 0)

    def test_extract_keywords_tfidf_empty_corpus_and_bad_index(self) -> None:
        """Empty corpus or out-of-range target index yields no keywords."""
        self.assertEqual(extract_keywords_tfidf([], target_index=0), [])
        docs = ["alpha beta"]
        self.assertEqual(extract_keywords_tfidf(docs, target_index=5), [])

    def test_extract_keywords_tfidf_empty_target_document(self) -> None:
        """A target document with no usable tokens returns an empty list."""
        docs = ["the and of", "alpha beta gamma"]
        self.assertEqual(extract_keywords_tfidf(docs, target_index=0), [])

    def test_extract_keywords_tfidf_bigram_scoring(self) -> None:
        """TF-IDF bigram mode scores distinctive phrases highest."""
        docs = [
            "machine learning rocks machine learning",
            "cooking pasta dishes tonight",
            "gardening tips for spring blooms",
        ]
        keywords = extract_keywords_tfidf(docs, target_index=0, ngram_size=2, top_n=5)
        self.assertTrue(any(kw == "machine learning" for kw, _ in keywords))


class TestKeywordExtractorCli(unittest.TestCase):
    """End-to-end tests for build_parser and the main() entry point."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.work = Path(self.tmp_dir.name)

    def _write_doc(self, name: str, content: str) -> Path:
        path = self.work / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_build_parser_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([str(self.work / "doc.txt")])
        self.assertEqual(args.method, "tf")
        self.assertEqual(args.ngram, 1)
        self.assertEqual(args.top, 10)
        self.assertFalse(args.json_output)

    def test_main_missing_file_returns_error(self) -> None:
        rc = main([str(self.work / "nope.txt")])
        self.assertEqual(rc, 1)

    def test_main_tf_plain_output(self) -> None:
        doc = self._write_doc(
            "doc.txt", "Python Python Python code code data data data data"
        )
        rc = main([str(doc)])
        self.assertEqual(rc, 0)

    def test_main_json_output_matches_ranking(self) -> None:
        doc = self._write_doc(
            "doc.txt", "Python Python Python code code data data data data"
        )
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--json", "--top", "2", str(doc)])
        self.assertEqual(rc, 0)
        payload: List[Dict[str, Any]] = json.loads(buf.getvalue())
        self.assertEqual(len(payload), 2)
        self.assertIn(payload[0]["keyword"], ("data", "python"))
        self.assertIsInstance(payload[0]["score"], float)

    def test_main_tfidf_splits_paragraphs_into_corpus(self) -> None:
        doc = self._write_doc(
            "report.txt",
            "Quantum computing quantum physics.\n\n"
            "Cooking recipes and baking.\n\nGardening tips outdoors.",
        )
        rc = main(["--method", "tfidf", str(doc)])
        self.assertEqual(rc, 0)

    def test_main_tfidf_falls_back_to_lines_for_single_paragraph(self) -> None:
        doc = self._write_doc(
            "single.txt",
            "quantum quantum state\ncooking recipes tonight\ngardening spring",
        )
        rc = main(["--method", "tfidf", str(doc)])
        self.assertEqual(rc, 0)

    def test_main_empty_file_succeeds_without_output(self) -> None:
        import io
        from contextlib import redirect_stdout

        doc = self._write_doc("empty.txt", "")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([str(doc)])
        self.assertEqual(rc, 0)
        self.assertIn("Top 0 Keywords", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Plagiarism Detector."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from main import (
    analyze_plagiarism,
    calculate_containment,
    calculate_cosine_similarity,
    calculate_jaccard_similarity,
    find_matching_snippets,
    generate_ngrams,
    main,
    parse_args,
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


class TestSimilarityEdgeCases(unittest.TestCase):
    """Edge-case coverage for similarity helpers."""

    def test_generate_ngrams_shorter_than_window(self) -> None:
        self.assertEqual(generate_ngrams(["one", "two"], n=3), [])

    def test_jaccard_with_empty_sets(self) -> None:
        self.assertEqual(calculate_jaccard_similarity(set(), set()), 1.0)
        self.assertEqual(calculate_jaccard_similarity({("a",)}, set()), 0.0)

    def test_containment_with_empty_target(self) -> None:
        self.assertEqual(calculate_containment({("a", "b")}, set()), 0.0)

    def test_cosine_with_empty_documents(self) -> None:
        self.assertEqual(calculate_cosine_similarity([], ["word"]), 0.0)
        self.assertEqual(calculate_cosine_similarity(["word"], []), 0.0)

    def test_find_matching_snippets_without_overlap(self) -> None:
        w1 = tokenize("alpha beta gamma delta")
        w2 = tokenize("echo foxtrot golf hotel")
        self.assertEqual(find_matching_snippets(w1, w2, min_length=3), [])

    def test_parse_args_defaults_and_overrides(self) -> None:
        parsed = parse_args(["a.txt", "b.txt"])
        self.assertEqual(parsed.file1, Path("a.txt"))
        self.assertEqual(parsed.file2, Path("b.txt"))
        self.assertEqual(parsed.ngram, 3)
        self.assertFalse(parsed.json_output)

        parsed = parse_args(["a.txt", "b.txt", "--ngram", "5", "--json"])
        self.assertEqual(parsed.ngram, 5)
        self.assertTrue(parsed.json_output)


class TestPlagiarismCli(unittest.TestCase):
    """End-to-end CLI tests for the plagiarism detector."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_main_missing_file_returns_error(self) -> None:
        real = self._write("real.txt", "some content here")
        missing = str(self.root / "ghost.txt")
        for args in ([missing, str(real)], [str(real), missing]):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                ret = main(args)
            self.assertEqual(ret, 1)
            self.assertIn("do not exist", buf.getvalue())

    def test_main_text_report_lists_matching_snippets(self) -> None:
        doc1 = self._write(
            "doc1.txt",
            "the quick brown fox jumps over the lazy dog near the river bank",
        )
        doc2 = self._write(
            "doc2.txt",
            "yesterday the quick brown fox jumps over the lazy dog again",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main([str(doc1), str(doc2)])
        self.assertEqual(ret, 0)
        output = buf.getvalue()
        self.assertIn("Plagiarism & Similarity Report", output)
        self.assertIn("Sample Matching Snippets:", output)
        self.assertIn("quick brown fox", output)

    def test_main_json_report_output(self) -> None:
        doc1 = self._write("doc1.txt", "shared phrase sequence appears here now")
        doc2 = self._write("doc2.txt", "shared phrase sequence appears here now")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["--ngram", "2", "--json", str(doc1), str(doc2)])
        self.assertEqual(ret, 0)
        report = json.loads(buf.getvalue())
        self.assertEqual(report["similarity_percentage"], 100.0)
        self.assertGreater(report["matching_snippets_count"], 0)


if __name__ == "__main__":
    unittest.main()

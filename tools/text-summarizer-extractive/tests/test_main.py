"""Extended tests for the Extractive Text Summarizer."""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple
from unittest import mock

from main import (
    build_parser,
    calculate_word_frequencies,
    main,
    score_sentences,
    split_sentences,
    summarize,
)


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


class TestWordFrequencies(unittest.TestCase):
    """Frequency calculation edge cases."""

    def test_stop_word_only_text_returns_empty_dict(self) -> None:
        """Text containing only stop words produces no frequency entries."""
        self.assertEqual(calculate_word_frequencies("the and it was to"), {})

    def test_custom_stop_words_are_respected(self) -> None:
        """Caller-provided stop word sets replace the default list."""
        freqs = calculate_word_frequencies("alpha beta alpha", stop_words={"beta"})
        self.assertEqual(freqs, {"alpha": 1.0})

    def test_single_character_tokens_are_ignored(self) -> None:
        """Tokens shorter than two letters never enter the counts."""
        freqs = calculate_word_frequencies("a I go go")
        self.assertEqual(freqs, {"go": 1.0})

    def test_frequencies_normalized_to_maximum(self) -> None:
        """The most frequent word scores exactly 1.0."""
        freqs = calculate_word_frequencies("dog cat cat dog dog bird")
        self.assertEqual(freqs["dog"], 1.0)
        self.assertAlmostEqual(freqs["cat"], 2 / 3)


class TestSentenceScoring(unittest.TestCase):
    """Scoring behavior for individual sentences."""

    def test_sentence_without_words_scores_zero(self) -> None:
        """Sentences with no alphabetic words receive a zero score."""
        self.assertEqual(score_sentences(["123 456!!!"], {"word": 1.0}), [0.0])

    def test_scores_use_length_normalization(self) -> None:
        """Scores divide by the square root of sentence word count."""
        freqs = {"data": 1.0, "rocks": 0.5}
        short = score_sentences(["Data rocks!"], freqs)[0]
        long_sent = score_sentences(["Data rocks the whole wide world today"], freqs)[0]
        self.assertGreater(short, long_sent)

    def test_unknown_words_contribute_nothing(self) -> None:
        """Words missing from the frequency map add zero to the total."""
        self.assertEqual(score_sentences(["zzz qqq"], {"known": 1.0})[0], 0.0)


class TestSummarizeEdgeCases(unittest.TestCase):
    """Summarizer boundary conditions."""

    SHORT_TEXT = "Only one sentence here. And a second one follows."

    def test_short_texts_returned_verbatim(self) -> None:
        """Texts with at most two sentences are returned unchanged."""
        self.assertEqual(summarize(self.SHORT_TEXT), self.SHORT_TEXT.strip())

    def test_num_sentences_clamped_to_available(self) -> None:
        """Requested counts above the total return every sentence."""
        text = "Alpha beta gamma delta. Epsilon zeta eta theta. Iota kappa lambda mu."
        summary = summarize(text, num_sentences=99)
        self.assertEqual(len(split_sentences(summary)), 3)

    def test_ratio_always_yields_at_least_one_sentence(self) -> None:
        """Tiny ratios still select a single best sentence."""
        text = "One two three four five. Six seven eight nine ten. "
        text += "Eleven twelve thirteen fourteen fifteen."
        summary = summarize(text, ratio=0.01)
        self.assertGreaterEqual(len(split_sentences(summary)), 1)


class TestParser(unittest.TestCase):
    """CLI argument parsing."""

    def test_defaults_and_optional_flags(self) -> None:
        """file is positional; ratio/output/sentences carry defaults."""
        parsed = build_parser().parse_args(["doc.txt"])
        self.assertEqual(str(parsed.file), "doc.txt")
        self.assertAlmostEqual(parsed.ratio, 0.3)
        self.assertIsNone(parsed.sentences)
        self.assertIsNone(parsed.output)
        tuned = build_parser().parse_args(
            ["doc.txt", "--ratio", "0.5", "--sentences", "4", "--output", "sum.txt"]
        )
        self.assertAlmostEqual(tuned.ratio, 0.5)
        self.assertEqual(tuned.sentences, 4)
        self.assertEqual(str(tuned.output), "sum.txt")


class TestMainCli(unittest.TestCase):
    """End-to-end CLI behavior with temporary documents."""

    DOCUMENT = (
        "Extractive summarization selects important sentences from a document. "
        "The scoring uses normalized word frequency statistics across sentences. "
        "Sentences with frequent content words receive higher importance scores. "
        "The final summary joins the top ranked sentences in original order. "
        "This approach keeps summaries faithful to the source material. "
        "Random noise sentences should rarely rank highly in the output. "
        "Testing confirms deterministic selection for stable inputs. "
        "Summaries help readers digest long reports quickly and reliably."
    )

    @staticmethod
    def write_doc(content: str, suffix: str = ".txt") -> str:
        """Write ``content`` into a temp file and return its path."""
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        )
        handle.write(content)
        handle.close()
        return handle.name

    def run_cli(self, argv: List[str]) -> Tuple[int, str, str]:
        """Run main() capturing stdout/stderr; removes first temp input."""
        out_buf, err_buf = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out_buf):
                with contextlib.redirect_stderr(err_buf):
                    code = main(argv)
        finally:
            if os.path.exists(argv[0]):
                os.unlink(argv[0])
        return code, out_buf.getvalue(), err_buf.getvalue()

    def test_missing_file_reports_error(self) -> None:
        """Unknown input files print an error and return exit code 1."""
        code, _, err = self.run_cli(["ghost-document.txt"])
        self.assertEqual(code, 1)
        self.assertIn("Error: File 'ghost-document.txt' not found.", err)

    def test_summary_printed_to_stdout(self) -> None:
        """Default invocation prints a labeled summary block."""
        path = self.write_doc(self.DOCUMENT)
        code, out, _ = self.run_cli([path, "--sentences", "2"])
        self.assertEqual(code, 0)
        self.assertIn("--- Summary ---", out)
        self.assertTrue(out.split("--- Summary ---")[1].strip())

    def test_output_flag_writes_summary_file(self) -> None:
        """--output saves the summary and prints the destination path."""
        doc_path = self.write_doc(self.DOCUMENT)
        summary_path = doc_path + ".summary"
        try:
            code, out, _ = self.run_cli(
                [doc_path, "--output", summary_path, "--sentences", "3"]
            )
            saved = Path(summary_path).read_text(encoding="utf-8")
        finally:
            if os.path.exists(summary_path):
                os.unlink(summary_path)
        self.assertEqual(code, 0)
        self.assertIn(f"Summary written to {summary_path}", out)
        self.assertEqual(len(split_sentences(saved)), 3)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program summarizes a temp document."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        doc_path = self.write_doc(self.DOCUMENT)
        buffer = io.StringIO()
        argv = [entry, doc_path, "--sentences", "2"]
        try:
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as ctx:
                        runpy.run_path(entry, run_name="__main__")
        finally:
            if os.path.exists(doc_path):
                os.unlink(doc_path)
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("--- Summary ---", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

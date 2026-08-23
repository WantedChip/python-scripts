"""Unit tests for Basic Sentiment Analyzer."""

import contextlib
import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple
from unittest import mock

from main import analyze_sentiment, build_parser, load_custom_lexicon, main, tokenize


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

    def test_tokenize_empty_text_returns_empty_list(self) -> None:
        """Empty input tokenizes to no words."""
        self.assertEqual(tokenize(""), [])

    def test_empty_text_is_fully_neutral(self) -> None:
        """Empty text yields zero scores and a neutral ratio of one."""
        res = analyze_sentiment("")
        self.assertEqual(res["overall_sentiment"], "Neutral")
        self.assertEqual(res["total_words"], 0)
        self.assertEqual(res["ratios"]["neutral"], 1.0)
        self.assertEqual(res["ratios"]["positive"], 0.0)

    def test_custom_lexicon_sets_override_defaults(self) -> None:
        """Custom word sets replace the built-in defaults entirely."""
        res = analyze_sentiment(
            "zorp flib",
            positive_words={"zorp"},
            negative_words={"flib"},
            negators={"nope"},
        )
        self.assertEqual(res["matched_positive"], ["zorp"])
        self.assertEqual(res["matched_negative"], ["flib"])
        self.assertEqual(res["net_score"], 0)
        self.assertEqual(res["ratios"]["positive"], 0.5)
        self.assertEqual(res["ratios"]["negative"], 0.5)


class TestLoadCustomLexicon(unittest.TestCase):
    """Tests for reading lexicon JSON files."""

    def write_lexicon(self, payload: str) -> Path:
        """Write ``payload`` to a temp JSON file and return its path."""
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        handle.write(payload)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return Path(handle.name)

    def test_loads_positive_and_negative_sets(self) -> None:
        """Both word lists round-trip through the loader."""
        path = self.write_lexicon(
            '{"positive": ["snazzy", "zesty"], "negative": ["bleh"]}'
        )
        pos, neg = load_custom_lexicon(path)
        self.assertEqual(pos, {"snazzy", "zesty"})
        self.assertEqual(neg, {"bleh"})

    def test_missing_keys_default_to_empty_sets(self) -> None:
        """Absent sections load as empty sets instead of failing."""
        path = self.write_lexicon('{"positive": ["solo"]}')
        pos, neg = load_custom_lexicon(path)
        self.assertEqual(pos, {"solo"})
        self.assertEqual(neg, set())


class TestParser(unittest.TestCase):
    """Tests for CLI argument parsing rules."""

    def test_text_and_file_are_mutually_exclusive_and_required(self) -> None:
        """One of --text or --file must be supplied, never both."""
        parser = build_parser()
        parsed = parser.parse_args(["--text", "great stuff"])
        self.assertEqual(parsed.text, "great stuff")
        with self.assertRaises(SystemExit):
            parser.parse_args(["--text", "a", "--file", "b.txt"])

    def test_optional_flags_parse(self) -> None:
        """--lexicon and --json attach their values correctly."""
        parsed = build_parser().parse_args(
            ["--text", "hi", "--lexicon", "words.json", "--json"]
        )
        self.assertEqual(str(parsed.lexicon), "words.json")
        self.assertTrue(parsed.json_output)


class TestMainCli(unittest.TestCase):
    """End-to-end tests for the command line interface."""

    def capture(self, args: List[str]) -> Tuple[int, str, str]:
        """Run main() capturing stdout and stderr."""
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf):
            with contextlib.redirect_stderr(err_buf):
                code = main(args)
        return code, out_buf.getvalue(), err_buf.getvalue()

    def test_text_report_output(self) -> None:
        """Default output is a formatted human-readable report."""
        code, out, _ = self.capture(["--text", "I love this, it is amazing"])
        self.assertEqual(code, 0)
        self.assertIn("--- Sentiment Analysis Report ---", out)
        self.assertIn("Overall Sentiment: Positive", out)
        self.assertIn("Positive Matches : 2 ['love', 'amazing']", out)

    def test_json_output_flag(self) -> None:
        """--json emits machine-readable analysis results."""
        code, out, _ = self.capture(["--text", "horrible waste", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["overall_sentiment"], "Negative")
        self.assertEqual(payload["net_score"], -2)

    def test_missing_text_file_returns_one(self) -> None:
        """A nonexistent --file writes an error and returns exit code 1."""
        code, _, err = self.capture(["--file", "definitely-missing.txt"])
        self.assertEqual(code, 1)
        self.assertIn("Error: Text file", err)

    def test_existing_text_file_is_analyzed(self) -> None:
        """A real --file has its contents read and analyzed."""
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        handle.write("the food was delicious and the staff friendly")
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        code, out, _ = self.capture(["--file", handle.name])
        self.assertEqual(code, 0)
        self.assertIn("Overall Sentiment: Positive", out)

    def test_missing_lexicon_returns_one(self) -> None:
        """A nonexistent --lexicon writes an error and returns exit code 1."""
        code, _, err = self.capture(
            ["--text", "good", "--lexicon", "no-such-lexicon.json"]
        )
        self.assertEqual(code, 1)
        self.assertIn("Error: Lexicon file", err)

    def test_custom_lexicon_changes_results(self) -> None:
        """A provided lexicon drives which words count as positive."""
        lex_handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        lex_handle.write('{"positive": ["blorpish"], "negative": []}')
        lex_handle.close()
        self.addCleanup(os.unlink, lex_handle.name)
        code, out, _ = self.capture(
            ["--text", "totally blorpish experience", "--lexicon", lex_handle.name]
        )
        self.assertEqual(code, 0)
        self.assertIn("Overall Sentiment: Positive", out)
        self.assertIn("'blorpish'", out)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program analyzes the given text."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        argv = [entry, "--text", "wonderful"]
        out_buf = io.StringIO()
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(out_buf):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(entry, run_name="__main__")
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Sentiment Analysis Report", out_buf.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Word Frequency Counter."""

import json
import tempfile
import unittest
from pathlib import Path

from main import filter_and_count, format_json, load_stop_words, parse_args, tokenize


class TestWordFrequencyCounter(unittest.TestCase):
    """Test suite for Word Frequency Counter."""

    def test_tokenize(self) -> None:
        text = "Hello world! This is a test, hello again."
        tokens = tokenize(text, lower=True)
        expected = [
            "hello",
            "world",
            "this",
            "is",
            "a",
            "test",
            "hello",
            "again",
        ]
        self.assertEqual(tokens, expected)

    def test_filter_and_count(self) -> None:
        tokens = ["python", "code", "python", "the", "a", "script"]
        stop_words = {"the", "a"}

        counter = filter_and_count(
            tokens, stop_words, min_length=2, ignore_stop_words=True
        )
        self.assertEqual(counter["python"], 2)
        self.assertEqual(counter["code"], 1)
        self.assertNotIn("the", counter)
        self.assertNotIn("a", counter)

    def test_format_json(self) -> None:
        counts = [("python", 5), ("code", 3)]
        json_output = format_json(counts, total_words=8)
        data = json.loads(json_output)

        self.assertEqual(data["total_tokens"], 8)
        self.assertEqual(len(data["rankings"]), 2)
        self.assertEqual(data["rankings"][0]["word"], "python")

    def test_load_custom_stop_words(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
            f.write("customword\nanotherword\n")
            temp_path = Path(f.name)

        try:
            stop_words = load_stop_words(temp_path)
            self.assertIn("customword", stop_words)
            self.assertIn("anotherword", stop_words)
            self.assertIn("the", stop_words)  # default stop words still present
        finally:
            temp_path.unlink()

    def test_parse_args(self) -> None:
        cmd_args = ["sample.txt", "--top", "5", "--format", "json", "-m", "3"]
        args = parse_args(cmd_args)
        self.assertEqual(args.input_file, "sample.txt")
        self.assertEqual(args.top, 5)
        self.assertEqual(args.format, "json")
        self.assertEqual(args.min_length, 3)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Text Case Converter."""

import tempfile
import unittest
from pathlib import Path

from main import (
    convert_text,
    parse_args,
    to_camelcase,
    to_kebabcase,
    to_lowercase,
    to_sentencecase,
    to_snakecase,
    to_titlecase,
    to_uppercase,
)


class TestTextCaseConverter(unittest.TestCase):
    """Test suite for Text Case Converter functions."""

    def test_casing_transformations(self) -> None:
        raw = "hello_world testCase"

        self.assertEqual(to_lowercase(raw), "hello_world testcase")
        self.assertEqual(to_uppercase(raw), "HELLO_WORLD TESTCASE")
        self.assertEqual(to_titlecase("hello world"), "Hello World")
        self.assertEqual(to_camelcase(raw), "helloWorldTestCase")
        self.assertEqual(to_snakecase(raw), "hello_world_test_case")
        self.assertEqual(to_kebabcase(raw), "hello-world-test-case")

    def test_sentence_case(self) -> None:
        text = "hello world. this is a TEST!"
        res = to_sentencecase(text)
        self.assertIn("Hello world.", res)
        self.assertIn("This is a test!", res)

    def test_convert_text_function(self) -> None:
        res = convert_text("someVariable_name", "camel")
        self.assertEqual(res, "someVariableName")

    def test_file_in_place(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
            f.write("hello_world")
            temp_path = Path(f.name)

        try:
            converted = convert_text(temp_path.read_text(), "upper")
            temp_path.write_text(converted)
            self.assertEqual(temp_path.read_text(), "HELLO_WORLD")
        finally:
            temp_path.unlink()

    def test_parse_args(self) -> None:
        args = parse_args(["file.txt", "--mode", "snake", "--in-place"])
        self.assertEqual(args.input_file, "file.txt")
        self.assertEqual(args.mode, "snake")
        self.assertTrue(args.in_place)


if __name__ == "__main__":
    unittest.main()

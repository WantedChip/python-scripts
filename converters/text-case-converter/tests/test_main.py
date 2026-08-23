"""Unit tests for Text Case Converter."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from main import (
    convert_text,
    main,
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


class TestConvertTextModes(unittest.TestCase):
    """Dispatch and error behaviour of convert_text."""

    def test_all_modes_dispatch_correctly(self) -> None:
        """Every documented mode (and alias) maps to its transformer."""
        text = "hello big World"
        self.assertEqual(convert_text(text, "lower"), "hello big world")
        self.assertEqual(convert_text(text, "lowercase"), "hello big world")
        self.assertEqual(convert_text(text, "upper"), "HELLO BIG WORLD")
        self.assertEqual(convert_text(text, "uppercase"), "HELLO BIG WORLD")
        self.assertEqual(convert_text("hello world", "title"), "Hello World")
        self.assertEqual(convert_text("hello world", "titlecase"), "Hello World")
        self.assertEqual(convert_text(text, "camel"), "helloBigWorld")
        self.assertEqual(convert_text(text, "camelcase"), "helloBigWorld")
        self.assertEqual(convert_text(text, "snake"), "hello_big_world")
        self.assertEqual(convert_text(text, "snakecase"), "hello_big_world")
        self.assertEqual(convert_text(text, "kebab"), "hello-big-world")
        self.assertEqual(convert_text(text, "kebabcase"), "hello-big-world")
        self.assertEqual(convert_text("hi there. ok go", "sentence"), "Hi there. Ok go")
        self.assertEqual(convert_text("a-b", "sentencecase"), "A-b")

    def test_unsupported_mode_raises_value_error(self) -> None:
        """Unknown modes raise ValueError with the mode named."""
        with self.assertRaises(ValueError):
            convert_text("anything", "rot13")


class TestNewlinePreservation(unittest.TestCase):
    """Multi-line conversions keep blank lines and trailing newlines."""

    def test_camelcase_preserves_blank_lines(self) -> None:
        """Empty lines pass through camelCase conversion untouched."""
        self.assertEqual(to_camelcase("foo bar\n\nbaz qux\n"), "fooBar\n\nbazQux\n")

    def test_snakecase_preserves_blank_lines(self) -> None:
        """Empty lines pass through snake_case conversion untouched."""
        self.assertEqual(to_snakecase("Foo Bar\n\nBaz Qux\n"), "foo_bar\n\nbaz_qux\n")

    def test_kebabcase_preserves_blank_lines(self) -> None:
        """Empty lines pass through kebab-case conversion untouched."""
        self.assertEqual(to_kebabcase("Foo Bar\n\nBaz Qux\n"), "foo-bar\n\nbaz-qux\n")

    def test_sentencecase_preserves_blank_lines(self) -> None:
        """Blank lines survive sentence-case conversion."""
        result = to_sentencecase("first one.\n\nsecond one!\n")
        self.assertEqual(result, "First one.\n\nSecond one!\n")

    def test_sentencecase_indented_fragment(self) -> None:
        """Leading indentation of a sentence is preserved."""
        result = to_sentencecase("  hello there.  again here.")
        self.assertIn("Hello there.", result)
        self.assertIn("Again here.", result)


class _FakeStdin(io.StringIO):
    """Stdin stand-in that reports not-a-tty."""

    def isatty(self) -> bool:
        return False


class _InteractiveStdin(io.StringIO):
    """Stdin stand-in that reports an interactive terminal."""

    def isatty(self) -> bool:
        return True


class TestTextCaseConverterCli(unittest.TestCase):
    """CLI-level tests covering main() input/output routing."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.input_file = self.dir_path / "notes.txt"
        self.output_file = self.dir_path / "out.txt"
        self.input_file.write_text("hello_world foo bar", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_main_writes_output_file(self) -> None:
        """--output writes converted text to a new file."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    str(self.input_file),
                    "--mode",
                    "upper",
                    "--output",
                    str(self.output_file),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            self.output_file.read_text(encoding="utf-8"), "HELLO_WORLD FOO BAR"
        )
        self.assertIn("Successfully wrote output", stdout.getvalue())

    def test_main_prints_to_stdout_by_default(self) -> None:
        """Without --output the converted text streams to stdout."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(self.input_file), "--mode", "snake"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "hello_world_foo_bar")

    def test_main_in_place_rewrites_source(self) -> None:
        """--in-place replaces the source file content."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(self.input_file), "--mode", "kebab", "--in-place"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            self.input_file.read_text(encoding="utf-8"), "hello-world-foo-bar"
        )
        self.assertIn("in-place", stdout.getvalue())

    def test_main_missing_input_file_returns_error(self) -> None:
        """Nonexistent inputs return exit code 1 via stderr."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(["missing.txt", "--mode", "lower"])

        self.assertEqual(exit_code, 1)
        self.assertIn("File not found", stderr.getvalue())

    def test_main_reads_piped_stdin(self) -> None:
        """Piped stdin is consumed when no input file is given."""
        stdout = io.StringIO()
        with redirect_stdout(stdout), mock.patch(
            "main.sys.stdin", _FakeStdin("Pipe Case Text")
        ):
            exit_code = main(["--mode", "camel"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "pipeCaseText")

    def test_main_interactive_stdin_returns_error(self) -> None:
        """Interactive stdin without a file aborts with exit code 1."""
        stderr = io.StringIO()
        with redirect_stderr(stderr), mock.patch(
            "main.sys.stdin", _InteractiveStdin("")
        ):
            exit_code = main(["--mode", "lower"])

        self.assertEqual(exit_code, 1)
        self.assertIn("stdin is interactive", stderr.getvalue())

    def test_main_in_place_with_stdin_returns_error(self) -> None:
        """--in-place cannot be combined with stdin input."""
        stderr = io.StringIO()
        with redirect_stderr(stderr), mock.patch("main.sys.stdin", _FakeStdin("text")):
            exit_code = main(["--mode", "lower", "--in-place"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Cannot use --in-place with stdin", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    FALLBACK_QUOTES,
    append_quote_to_file,
    build_parser,
    fetch_quote_from_api,
    format_quote_markdown,
    is_quote_duplicate,
    main,
)


def _urlopen_result(payload: Any) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = 200
    body = payload if isinstance(payload, str) else json.dumps(payload)
    resp.read.return_value = body.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


class TestQuoteOfTheDayScraper(unittest.TestCase):
    """Unit tests for Quote of the Day Scraper."""

    def test_format_quote_markdown(self):
        md = format_quote_markdown(
            "Life is simple.", "Anonymous", category="Philosophy"
        )
        self.assertIn('> "Life is simple."', md)
        self.assertIn("> — **Anonymous**", md)
        self.assertIn("Category: Philosophy", md)
        self.assertIn("---", md)

    def test_is_quote_duplicate(self):
        existing = (
            '> "The best way to predict the future is to create it."\n'
            "> — **Peter Drucker**"
        )
        self.assertTrue(
            is_quote_duplicate(
                existing, "The best way to predict the future is to create it."
            )
        )
        self.assertFalse(is_quote_duplicate(existing, "Knowledge is power."))

    def test_append_quote_to_file_and_deduplicate(self):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".md") as tmp:
            tmp_path = tmp.name

        try:
            # First append should succeed
            res1 = append_quote_to_file(
                tmp_path, "Stay hungry, stay foolish.", "Steve Jobs"
            )
            self.assertTrue(res1)

            # Duplicate append should be rejected
            res2 = append_quote_to_file(
                tmp_path, "Stay hungry, stay foolish.", "Steve Jobs"
            )
            self.assertFalse(res2)

            # Force append should succeed
            res3 = append_quote_to_file(
                tmp_path,
                "Stay hungry, stay foolish.",
                "Steve Jobs",
                force=True,
            )
            self.assertTrue(res3)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestFetchQuoteFromApi(unittest.TestCase):
    """Provider-specific API payload parsing with mocked HTTP."""

    def test_zenquotes_list_payload(self) -> None:
        payload = [
            {"q": "Simplicity is the soul of efficiency.", "a": "Austin Freeman"}
        ]
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(payload)
        ):
            quote = fetch_quote_from_api("zenquotes")
        self.assertEqual(quote["quote"], "Simplicity is the soul of efficiency.")
        self.assertEqual(quote["author"], "Austin Freeman")

    def test_dummyjson_dict_payload(self) -> None:
        payload = {"quote": "Do the hard jobs first.", "author": "Dale Carnegie"}
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(payload)
        ):
            quote = fetch_quote_from_api("dummyjson")
        self.assertEqual(quote["quote"], "Do the hard jobs first.")
        self.assertEqual(quote["author"], "Dale Carnegie")

    def test_quotable_content_key(self) -> None:
        """The quotable provider stores the text under 'content'."""
        payload = {"content": "Talk is cheap. Show me the code.", "author": "Linus"}
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(payload)
        ):
            quote = fetch_quote_from_api("quotable")
        self.assertEqual(quote["quote"], "Talk is cheap. Show me the code.")
        self.assertEqual(quote["author"], "Linus")

    def test_unknown_source_falls_back_to_zenquotes_endpoint(self) -> None:
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result([])
        ) as mock_open:
            fetch_quote_from_api("mystery-source")
        requested_url = mock_open.call_args.args[0].full_url
        self.assertTrue(requested_url.startswith("https://zenquotes.io/api/today"))

    def test_network_error_returns_builtin_fallback(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            quote = fetch_quote_from_api("zenquotes")
        self.assertIn(quote, FALLBACK_QUOTES)

    def test_malformed_json_returns_builtin_fallback(self) -> None:
        resp = _urlopen_result("{broken json")
        with patch("main.urllib.request.urlopen", return_value=resp):
            quote = fetch_quote_from_api("dummyjson")
        self.assertIn(quote, FALLBACK_QUOTES)


class TestAppendQuoteFileLayout(unittest.TestCase):
    """Markdown collection file layout rules."""

    def test_new_file_gets_collection_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "collection.md")
            self.assertTrue(append_quote_to_file(path, "Be curious.", "Unknown"))
            with open(path, encoding="utf-8") as f:
                content = f.read()
            self.assertTrue(content.startswith("# Personal Quote Collection\n\n"))
            self.assertIn('> "Be curious."', content)

    def test_format_without_category_omits_suffix(self) -> None:
        md = format_quote_markdown("Less is more.", "Mies")
        self.assertIn('> "Less is more."', md)
        self.assertNotIn("Category:", md)
        self.assertIn("*Added:", md)


class TestQuoteOfTheDayCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def test_build_parser_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.output, "quotes.md")
        self.assertEqual(args.source, "zenquotes")
        self.assertIsNone(args.category)
        self.assertFalse(args.force)

    def _run_main_capture(self, argv: list) -> tuple:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_main_appends_fetched_quote_to_collection(self) -> None:
        fetched = {
            "quote": "Perfection is achieved by subtraction.",
            "author": "Saint-Exupery",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "my_quotes.md")
            with patch("main.fetch_quote_from_api", return_value=fetched):
                code, out = self._run_main_capture(["-o", out_path])
            self.assertEqual(code, 0)
            self.assertIn(f"Successfully appended quote to {out_path}", out)
            with open(out_path, encoding="utf-8") as f:
                saved = f.read()
            self.assertIn("Perfection is achieved by subtraction.", saved)
            self.assertIn("**Saint-Exupery**", saved)

    def test_main_skips_duplicate_quote(self) -> None:
        fetched = {"quote": "Reuse beats rewrite.", "author": "Anon"}
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "dup.md")
            with patch("main.fetch_quote_from_api", return_value=fetched):
                code_first, _ = self._run_main_capture(["-o", out_path])
                code_second, out_second = self._run_main_capture(["-o", out_path])
            self.assertEqual(code_first, 0)
            self.assertEqual(code_second, 0)
            self.assertIn("Skipped entry", out_second)

    def test_main_force_flag_bypasses_deduplication(self) -> None:
        fetched = {"quote": "Twice is fine with force.", "author": "Tester"}
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "force.md")
            with patch("main.fetch_quote_from_api", return_value=fetched):
                code_one, _ = self._run_main_capture(["-o", out_path])
                code_two, out_two = self._run_main_capture(["--force", "-o", out_path])
            self.assertEqual(code_one, 0)
            self.assertEqual(code_two, 0)
            self.assertIn("Successfully appended", out_two)
            with open(out_path, encoding="utf-8") as f:
                occurrences = f.read().count("Twice is fine with force.")
            self.assertEqual(occurrences, 2)


if __name__ == "__main__":
    unittest.main()

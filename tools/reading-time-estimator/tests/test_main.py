"""Unit tests for Reading Time Estimator."""

import io
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from main import (
    build_parser,
    clean_html,
    count_words,
    estimate_reading_time,
    fetch_url_text,
    main,
)


class _FakeResponse:
    """Minimal stand-in for the object returned by urlopen()."""

    def __init__(self, payload: bytes, content_type: str, charset: Any = None):
        self.headers = MagicMock()
        self.headers.get.return_value = content_type
        self.headers.get_param.return_value = charset
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class TestReadingTimeEstimator(unittest.TestCase):
    """Test suite for reading time estimation and text extraction."""

    def test_word_count(self):
        text = "The quick brown fox jumps over the lazy dog."
        self.assertEqual(count_words(text), 9)

    def test_empty_word_count(self):
        self.assertEqual(count_words(""), 0)
        self.assertEqual(count_words("   \n\t  "), 0)

    def test_clean_html_extraction(self):
        html = "<html><body><h1>Title</h1><p>Hello <b>world</b>!</p></body></html>"
        extracted = clean_html(html)
        self.assertIn("Title", extracted)
        self.assertIn("Hello world", extracted)
        self.assertNotIn("<html>", extracted)

    def test_clean_html_with_script(self):
        html = "<p>Visible text</p><script>console.log('ignore me');</script>"
        extracted = clean_html(html)
        self.assertIn("Visible text", extracted)
        self.assertNotIn("ignore me", extracted)

    def test_reading_time_calculation(self):
        # 200 words at 200 wpm = 1 min (60 seconds)
        text = "word " * 200
        result = estimate_reading_time(text, wpm=200)
        self.assertEqual(result["word_count"], 200)
        self.assertEqual(result["minutes"], 1)
        self.assertEqual(result["seconds"], 0)
        self.assertEqual(result["formatted"], "1 min")

    def test_reading_time_short_text(self):
        # 50 words at 200 wpm = 15 seconds
        text = "word " * 50
        result = estimate_reading_time(text, wpm=200)
        self.assertEqual(result["minutes"], 0)
        self.assertEqual(result["seconds"], 15)
        self.assertEqual(result["formatted"], "15 sec")

    def test_invalid_wpm(self):
        with self.assertRaises(ValueError):
            estimate_reading_time("sample text", wpm=0)


class TestReadingTimeFormatting(unittest.TestCase):
    """Test suite for estimate formatting branches."""

    def test_zero_words_reports_zero_seconds(self) -> None:
        result: Dict[str, Any] = estimate_reading_time("!!! ... ???", wpm=200)
        self.assertEqual(result["word_count"], 0)
        self.assertEqual(result["total_seconds"], 0)
        self.assertEqual(result["formatted"], "0 seconds")

    def test_mixed_minutes_and_seconds_formatting(self) -> None:
        # 250 words at 200 wpm = 75 seconds -> "1 min 15 sec".
        result: Dict[str, Any] = estimate_reading_time("word " * 250, wpm=200)
        self.assertEqual(result["total_seconds"], 75)
        self.assertEqual(result["formatted"], "1 min 15 sec")


class TestHtmlCleaning(unittest.TestCase):
    """Test suite for HTML extraction fallback behavior."""

    def test_fallback_regex_strip_when_parser_fails(self) -> None:
        """If HTMLParser blows up, a regex tag-strip still yields text."""
        with patch("main.HTMLTextExtractor") as mock_extractor:
            mock_extractor.return_value.feed.side_effect = ValueError("boom")
            extracted = clean_html("<p>fallback <b>works</b></p>")
        self.assertIn("fallback", extracted)
        self.assertIn("works", extracted)


class TestUrlFetching(unittest.TestCase):
    """Test suite for fetch_url_text (network fully mocked)."""

    def test_html_content_is_cleaned(self) -> None:
        response = _FakeResponse(
            b"<html><body><h1>Hi</h1>"
            b"<script>x()</script><p>Body text</p></body></html>",
            content_type="text/html; charset=utf-8",
            charset="utf-8",
        )
        with patch("main.urllib.request.urlopen", return_value=response):
            text = fetch_url_text("https://example.com/post.html")
        self.assertIn("Hi Body text", text)
        self.assertNotIn("x()", text)

    def test_plain_text_content_passes_through(self) -> None:
        response = _FakeResponse(
            "café plain words here".encode("iso-8859-1"),
            content_type="text/plain; charset=iso-8859-1",
            charset="iso-8859-1",
        )
        with patch("main.urllib.request.urlopen", return_value=response):
            text = fetch_url_text("https://example.com/notes.txt")
        self.assertEqual(text, "café plain words here")

    def test_html_detected_without_content_type_header(self) -> None:
        response = _FakeResponse(
            b"<html><body>Sniffed html body</body></html>",
            content_type="",
            charset=None,
        )
        with patch("main.urllib.request.urlopen", return_value=response):
            text = fetch_url_text("https://example.com/page")
        self.assertIn("Sniffed html body", text)


class TestReadingTimeCli(unittest.TestCase):
    """End-to-end tests for build_parser and main()."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.work = Path(self.tmp_dir.name)

    def test_build_parser_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["doc.txt", "--wpm", "300"])
        self.assertEqual(args.source, "doc.txt")
        self.assertEqual(args.wpm, 300)

    def _run_main_capture(self, args: list) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(args)
        return rc, out.getvalue(), err.getvalue()

    def test_main_local_text_file(self) -> None:
        doc = self.work / "notes.txt"
        doc.write_text("word " * 100, encoding="utf-8")  # 30 s @ 200 wpm
        rc, out, _err = self._run_main_capture([str(doc)])
        self.assertEqual(rc, 0)
        self.assertIn("Word Count      : 100 words", out)
        self.assertIn("Estimated Time  : 30 sec (30 seconds)", out)

    def test_main_local_html_file_strips_markup(self) -> None:
        doc = self.work / "page.html"
        doc.write_text(
            "<html><head><title>Ignore</title></head>"
            "<body><p>Hello <b>world</b></p></body></html>",
            encoding="utf-8",
        )
        rc, out, _err = self._run_main_capture([str(doc)])
        self.assertEqual(rc, 0)
        self.assertIn("Word Count      : 2 words", out)

    def test_main_missing_file_returns_one(self) -> None:
        rc, _out, err = self._run_main_capture([str(self.work / "nope.txt")])
        self.assertEqual(rc, 1)
        self.assertIn("does not exist", err)

    def test_main_url_source_uses_fetcher(self) -> None:
        """URL sources are delegated to fetch_url_text (mocked)."""
        with patch("main.fetch_url_text", return_value="word " * 60) as mock_fetch:
            rc, out, _err = self._run_main_capture(["https://example.com/article"])
        self.assertEqual(rc, 0)
        mock_fetch.assert_called_once_with("https://example.com/article")
        self.assertIn("Fetching content from URL", out)
        self.assertIn("Word Count      : 60 words", out)

    def test_main_invalid_wpm_returns_one(self) -> None:
        doc = self.work / "short.txt"
        doc.write_text("hello there", encoding="utf-8")
        rc, _out, err = self._run_main_capture([str(doc), "--wpm", "0"])
        self.assertEqual(rc, 1)
        self.assertIn("Error processing input", err)

    def test_main_url_error_returns_one(self) -> None:
        with patch("main.urllib.request.urlopen") as mock_open:
            mock_open.side_effect = urllib.error.URLError("no dns")
            rc, _out, err = self._run_main_capture(["https://example.com/x"])
        self.assertEqual(rc, 1)
        self.assertIn("Error processing input", err)


if __name__ == "__main__":
    unittest.main()

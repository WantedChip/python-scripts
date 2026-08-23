"""Unit tests for Random Quote Fetcher tool."""

import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from main import (
    fetch_quote_from_api,
    fetch_quotes,
    format_quotes_markdown,
    format_quotes_text,
    main,
)


def _fake_response(payload: Any, status: int = 200) -> MagicMock:
    """Build a context-manager mock for urlopen returning JSON payload."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    return mock_cm


class TestRandomQuoteFetcher(unittest.TestCase):
    """Test suite for random quote fetcher functions."""

    @patch("urllib.request.urlopen")
    def test_fetch_quote_primary_success(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_data = [
            {
                "content": "Simplicity is prerequisite for reliability.",
                "author": "Edsger W. Dijkstra",
                "tags": ["technology", "programming"],
            }
        ]
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        quote = fetch_quote_from_api(tag="technology")
        self.assertEqual(quote["author"], "Edsger W. Dijkstra")
        self.assertIn("Simplicity", quote["content"])

    @patch("urllib.request.urlopen")
    def test_primary_query_includes_tag_and_author(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Tag and author filters are sent as query parameters."""
        mock_urlopen.return_value = _fake_response(
            [{"content": "c", "author": "a", "tags": []}]
        )
        fetch_quote_from_api(tag="Wisdom", author="Confucius")
        request = mock_urlopen.call_args[0][0]
        self.assertIn("tags=wisdom", request.full_url)
        self.assertIn("author=Confucius", request.full_url)

    @patch("urllib.request.urlopen")
    def test_primary_single_object_payload(self, mock_urlopen: MagicMock) -> None:
        """A single-object payload (not a list) is handled directly."""
        mock_urlopen.return_value = _fake_response(
            {"quote": "Talk is cheap.", "author": "Linus Torvalds"}
        )
        quote = fetch_quote_from_api()
        self.assertEqual(quote["content"], "Talk is cheap.")
        self.assertEqual(quote["author"], "Linus Torvalds")

    @patch("urllib.request.urlopen")
    def test_fallback_used_when_primary_raises(self, mock_urlopen: MagicMock) -> None:
        """Primary API transport errors fall through to DummyJSON."""
        broken = MagicMock()
        broken.status = 200
        broken.read.side_effect = urllib.error.URLError("reset by peer")
        mock_urlopen.side_effect = [
            broken,
            _fake_response({"quote": "Fallback wisdom.", "author": "Someone"}),
        ]
        quote = fetch_quote_from_api(tag="tech")
        self.assertEqual(quote["content"], "Fallback wisdom.")
        self.assertEqual(quote["author"], "Someone")
        self.assertEqual(quote["tags"], ["tech"])

    @patch("urllib.request.urlopen")
    def test_fallback_used_when_primary_non_200(self, mock_urlopen: MagicMock) -> None:
        """Primary non-200 responses fall through to DummyJSON."""
        mock_urlopen.side_effect = [
            _fake_response([], status=503),
            _fake_response({"quote": "Second chance.", "author": "Retry"}),
        ]
        quote = fetch_quote_from_api()
        self.assertEqual(quote["content"], "Second chance.")

    @patch("urllib.request.urlopen")
    def test_both_apis_failing_raises_runtime_error(
        self, mock_urlopen: MagicMock
    ) -> None:
        """When both APIs fail the failure is raised to the caller."""
        err = urllib.error.URLError("network down")
        mock_urlopen.side_effect = [err, err]
        with self.assertRaisesRegex(RuntimeError, "Failed to fetch quotes"):
            fetch_quote_from_api()

    @patch("urllib.request.urlopen")
    def test_fallback_non_200_returns_builtin_quote(
        self, mock_urlopen: MagicMock
    ) -> None:
        """If the fallback also misbehaves, a builtin quote is returned."""
        mock_urlopen.side_effect = [
            _fake_response({}, status=500),
            _fake_response({"nope": True}, status=500),
        ]
        quote = fetch_quote_from_api()
        self.assertEqual(quote["author"], "John Lennon")
        self.assertEqual(quote["tags"], [])

    def test_fetch_quotes_requests_each_quote(self) -> None:
        """fetch_quotes loops once per requested quote."""
        calls = []

        def fake_api(tag: Optional[str] = None, author: Optional[str] = None) -> dict:
            """Record each call and return a unique quote."""
            calls.append((tag, author))
            return {"content": f"q{len(calls)}", "author": "a", "tags": ["t"]}

        with patch("main.fetch_quote_from_api", side_effect=fake_api):
            quotes = fetch_quotes(count=3, tag="t", author="a")
        self.assertEqual(len(calls), 3)
        self.assertEqual([q["content"] for q in quotes], ["q1", "q2", "q3"])

    def test_format_quotes_text(self) -> None:
        quotes = [{"content": "Hello World", "author": "Coder", "tags": ["code"]}]
        text = format_quotes_text(quotes)
        self.assertIn('"Hello World"', text)
        self.assertIn("— Coder", text)

    def test_format_quotes_text_without_tags(self) -> None:
        """Quotes lacking tags render without a tag suffix."""
        text = format_quotes_text([{"content": "Hi", "author": "A", "tags": []}])
        self.assertNotIn("[", text)

    def test_format_quotes_markdown(self) -> None:
        quotes = [
            {
                "content": "Stay Hungry, Stay Foolish",
                "author": "Steve Jobs",
                "tags": ["inspirational"],
            }
        ]
        md = format_quotes_markdown(quotes)
        self.assertIn('> "Stay Hungry, Stay Foolish"', md)
        self.assertIn("**Steve Jobs**", md)


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    def _run_cli(self, *args: str) -> Any:
        """Run main() with patched argv; capture streams and exit code."""
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code: Any = None
        argv = ["main.py"] + list(args)
        with redirect_stdout(stdout), redirect_stderr(stderr), patch("sys.argv", argv):
            try:
                main()
            except SystemExit as exc:
                exit_code = exc.code
        return stdout.getvalue(), stderr.getvalue(), exit_code

    @patch("main.fetch_quotes")
    def test_cli_text_output_with_filters(self, mock_fetch: MagicMock) -> None:
        """Default text output renders the fetched quote block."""
        mock_fetch.return_value = [
            {"content": "Wise words.", "author": "Sage", "tags": ["wisdom"]}
        ]
        stdout, _, code = self._run_cli("-n", "1", "-t", "wisdom", "-a", "Sage")
        self.assertIsNone(code)
        self.assertIn('"Wise words."', stdout)
        self.assertIn("— Sage", stdout)
        self.assertIn("[wisdom]", stdout)
        mock_fetch.assert_called_once_with(count=1, tag="wisdom", author="Sage")

    @patch("main.fetch_quotes")
    def test_cli_markdown_and_json_formats(self, mock_fetch: MagicMock) -> None:
        """--format markdown/json switch the rendered representation."""
        mock_fetch.return_value = [
            {"content": "Deep thought.", "author": "Thinker", "tags": []}
        ]
        md_out, _, code_md = self._run_cli("-f", "markdown")
        json_out, _, code_json = self._run_cli("-f", "json")
        self.assertIsNone(code_md)
        self.assertIsNone(code_json)
        self.assertIn('> "Deep thought."', md_out)
        parsed = json.loads(json_out)
        self.assertEqual(parsed[0]["author"], "Thinker")

    @patch("main.fetch_quotes")
    def test_cli_output_file_write_and_append(self, mock_fetch: MagicMock) -> None:
        """-o writes files; --append prepends a blank-line separator."""
        mock_fetch.return_value = [
            {"content": "Persist me.", "author": "Disk", "tags": []}
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "quotes.txt")
            s1, _, c1 = self._run_cli("-o", out_path)
            s2, _, c2 = self._run_cli("-o", out_path, "--append")
            content = Path(out_path).read_text(encoding="utf-8")
        self.assertIsNone(c1)
        self.assertIsNone(c2)
        self.assertEqual(content.count('"Persist me."'), 2)
        self.assertIn('Disk\n\n"Persist me."', content)
        self.assertIn("Quotes successfully saved to", s2)

    @patch("main.fetch_quotes")
    def test_cli_error_exits_one(self, mock_fetch: MagicMock) -> None:
        """Quote failures print to stderr and exit 1."""
        mock_fetch.side_effect = RuntimeError("Failed to fetch quotes from APIs")
        _, stderr, code = self._run_cli()
        self.assertEqual(code, 1)
        self.assertIn("Error:", stderr)


if __name__ == "__main__":
    unittest.main()

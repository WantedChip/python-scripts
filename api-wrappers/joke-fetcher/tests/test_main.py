"""Unit tests for joke-fetcher main module."""

import io
import json
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from typing import Any
from unittest.mock import MagicMock, patch

from main import fetch_joke, format_joke_output, main, parse_joke


class TestJokeFetcher(unittest.TestCase):
    """Test cases for Joke Fetcher."""

    def test_parse_single_joke(self) -> None:
        """Test parsing a single-part joke payload."""
        raw = {
            "error": False,
            "category": "Programming",
            "type": "single",
            "joke": (
                "There are 10 types of people in the world: "
                "those who understand binary, and those who don't."
            ),
            "safe": True,
        }
        parsed = parse_joke(raw)
        self.assertFalse(parsed["error"])
        self.assertEqual(parsed["type"], "single")
        self.assertEqual(parsed["category"], "Programming")
        self.assertIn("10 types of people", parsed["joke"])

    def test_parse_twopart_joke(self) -> None:
        """Test parsing a two-part joke payload."""
        raw = {
            "error": False,
            "category": "Misc",
            "type": "twopart",
            "setup": "Why do programmers prefer dark mode?",
            "delivery": "Because light attracts bugs.",
            "safe": True,
        }
        parsed = parse_joke(raw)
        self.assertFalse(parsed["error"])
        self.assertEqual(parsed["type"], "twopart")
        self.assertEqual(parsed["setup"], "Why do programmers prefer dark mode?")
        self.assertEqual(parsed["delivery"], "Because light attracts bugs.")

    def test_format_joke_output_twopart(self) -> None:
        """Test formatting two-part joke output string."""
        parsed = {
            "error": False,
            "type": "twopart",
            "category": "Pun",
            "setup": "Setup line",
            "delivery": "Delivery line",
            "joke": "Setup line\nDelivery line",
        }
        formatted = format_joke_output(parsed)
        self.assertIn("Q: Setup line", formatted)
        self.assertIn("A: Delivery line", formatted)

    @patch("urllib.request.urlopen")
    def test_fetch_joke_api(self, mock_urlopen: MagicMock) -> None:
        """Test fetch_joke mock API call."""
        sample_api_response = {
            "error": False,
            "category": "Programming",
            "type": "single",
            "joke": "Mocked joke content",
            "safe": True,
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(sample_api_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_joke("Programming", safe_mode=True)
        self.assertIsNotNone(result)
        self.assertEqual(result["joke"], "Mocked joke content")
        request = mock_urlopen.call_args[0][0]
        self.assertIn("/joke/Programming?safe-mode", request.full_url)

    @patch("urllib.request.urlopen")
    def test_fetch_joke_unsafe_mode_omits_param(self, mock_urlopen: MagicMock) -> None:
        """Disabling safe mode drops the safe-mode query parameter."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"error": false}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        fetch_joke("Dark", safe_mode=False)
        request = mock_urlopen.call_args[0][0]
        self.assertIn("/joke/Dark", request.full_url)
        self.assertNotIn("safe-mode", request.full_url)

    @patch("urllib.request.urlopen")
    def test_fetch_joke_blank_category_defaults(self, mock_urlopen: MagicMock) -> None:
        """Blank categories fall back to the Programming endpoint."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"error": false}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        fetch_joke("   ")
        request = mock_urlopen.call_args[0][0]
        self.assertIn("/joke/Programming", request.full_url)

    @patch("urllib.request.urlopen")
    def test_fetch_joke_http_error_returns_none(self, mock_urlopen: MagicMock) -> None:
        """HTTP errors print a message and return None."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://v2.jokeapi.dev/joke/Programming",
            500,
            "Internal Server Error",
            None,
            io.BytesIO(b"oops"),
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_joke("Programming")
        self.assertIsNone(result)
        self.assertIn("HTTP Error 500", stderr.getvalue())

    @patch("urllib.request.urlopen")
    def test_fetch_joke_url_error_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Network errors print a message and return None."""
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_joke("Programming")
        self.assertIsNone(result)
        self.assertIn("Network Error:", stderr.getvalue())

    @patch("urllib.request.urlopen")
    def test_fetch_joke_timeout_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Unexpected transport exceptions are caught and mapped to None."""
        mock_urlopen.side_effect = TimeoutError("read timed out")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_joke("Programming")
        self.assertIsNone(result)
        self.assertIn("Error fetching joke", stderr.getvalue())

    @patch("urllib.request.urlopen")
    def test_fetch_joke_non_200_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Non-200 statuses yield None without raising."""
        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.read.return_value = b"slow down"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_joke("Programming"))

    def test_parse_error_payload(self) -> None:
        """API error payloads normalize to an error record."""
        raw = {"error": True, "message": "No jokes found for this category."}
        parsed = parse_joke(raw)
        self.assertTrue(parsed["error"])
        self.assertEqual(parsed["message"], "No jokes found for this category.")

    def test_format_error_output(self) -> None:
        """Error records render an [ERROR] banner."""
        formatted = format_joke_output({"error": True, "message": "broken"})
        self.assertEqual(formatted, "[ERROR] broken")

    def test_format_single_joke_output(self) -> None:
        """Single-part jokes render their body between separators."""
        parsed = {
            "error": False,
            "type": "single",
            "category": "Programming",
            "setup": None,
            "delivery": None,
            "joke": "A single punchline.",
        }
        formatted = format_joke_output(parsed)
        self.assertIn("JOKE (PROGRAMMING - SINGLE)", formatted.upper())
        self.assertIn("A single punchline.", formatted)


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

    @patch("main.fetch_joke")
    def test_cli_success_prints_twopart_joke(self, mock_fetch: MagicMock) -> None:
        """Successful runs print the formatted joke card."""
        mock_fetch.return_value = {
            "error": False,
            "category": "Pun",
            "type": "twopart",
            "setup": "Why six?",
            "delivery": "Because seven ate nine.",
        }
        stdout, _, code = self._run_cli("-c", "Pun")
        self.assertIsNone(code)
        self.assertIn("Q: Why six?", stdout)
        self.assertIn("A: Because seven ate nine.", stdout)
        mock_fetch.assert_called_once_with(category="Pun", safe_mode=True)

    @patch("main.fetch_joke")
    def test_cli_unsafe_flag_disables_safe_mode(self, mock_fetch: MagicMock) -> None:
        """--unsafe forwards safe_mode=False to the API call."""
        mock_fetch.return_value = {
            "error": False,
            "category": "Dark",
            "type": "single",
            "joke": "Edgy joke.",
        }
        stdout, _, code = self._run_cli("--unsafe", "-c", "Dark")
        self.assertIsNone(code)
        self.assertIn("Edgy joke.", stdout)
        mock_fetch.assert_called_once_with(category="Dark", safe_mode=False)

    @patch("main.fetch_joke")
    def test_cli_fetch_failure_exits_one(self, mock_fetch: MagicMock) -> None:
        """Failed lookups exit 1 without printing a joke card."""
        mock_fetch.return_value = None
        _, _, code = self._run_cli()
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

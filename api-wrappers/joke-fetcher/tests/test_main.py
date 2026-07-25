"""Unit tests for joke-fetcher main module."""

import json
import unittest
from unittest.mock import MagicMock, patch

from main import fetch_joke, format_joke_output, parse_joke


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


if __name__ == "__main__":
    unittest.main()

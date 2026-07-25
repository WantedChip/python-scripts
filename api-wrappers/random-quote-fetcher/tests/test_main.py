"""Unit tests for Random Quote Fetcher tool."""

import json
import unittest
from unittest.mock import MagicMock, patch

from main import fetch_quote_from_api, format_quotes_markdown, format_quotes_text


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

    def test_format_quotes_text(self) -> None:
        quotes = [{"content": "Hello World", "author": "Coder", "tags": ["code"]}]
        text = format_quotes_text(quotes)
        self.assertIn('"Hello World"', text)
        self.assertIn("— Coder", text)

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


if __name__ == "__main__":
    unittest.main()

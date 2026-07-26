"""
Unit tests for Dictionary Lookup CLI
"""

import unittest
from unittest.mock import MagicMock, patch

from main import DictionaryClient


class TestDictionaryClient(unittest.TestCase):
    def test_offline_lookup(self) -> None:
        client = DictionaryClient(offline_only=True)
        entries, source = client.lookup("python")
        self.assertEqual(source, "offline")
        self.assertIsNotNone(entries)
        self.assertEqual(entries[0]["word"], "python")

    def test_offline_missing_word(self) -> None:
        client = DictionaryClient(offline_only=True)
        entries, source = client.lookup("nonexistentword12345")
        self.assertEqual(source, "none")
        self.assertIsNone(entries)

    @patch("urllib.request.urlopen")
    def test_online_lookup(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_json_bytes = b'[{"word": "test", "meanings": []}]'
        mock_response.read.return_value = mock_json_bytes
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = DictionaryClient(offline_only=False)
        entries, source = client.lookup("test")
        self.assertEqual(source, "online")
        self.assertEqual(entries[0]["word"], "test")


if __name__ == "__main__":
    unittest.main()

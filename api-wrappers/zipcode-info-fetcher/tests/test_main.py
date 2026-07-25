"""Unit tests for zipcode-info-fetcher main module."""

import json
import unittest
from unittest.mock import MagicMock, patch

from main import export_to_json, fetch_zipcode_info, parse_place_details


class TestZipcodeInfoFetcher(unittest.TestCase):
    """Test suite for zipcode info fetcher functions."""

    def setUp(self) -> None:
        self.sample_raw_api_data = {
            "post code": "90210",
            "country": "United States",
            "country abbreviation": "US",
            "places": [
                {
                    "place name": "Beverly Hills",
                    "longitude": "-118.4065",
                    "state": "California",
                    "state abbreviation": "CA",
                    "latitude": "34.0901",
                }
            ],
        }

    def test_parse_place_details(self) -> None:
        """Test parsing raw API dictionary into structured dictionary."""
        result = parse_place_details(self.sample_raw_api_data)
        self.assertEqual(result["post_code"], "90210")
        self.assertEqual(result["country"], "United States")
        self.assertEqual(len(result["places"]), 1)
        self.assertEqual(result["places"][0]["place_name"], "Beverly Hills")
        self.assertEqual(result["places"][0]["latitude"], "34.0901")
        self.assertEqual(result["places"][0]["longitude"], "-118.4065")

    @patch("urllib.request.urlopen")
    def test_fetch_zipcode_info_success(self, mock_urlopen: MagicMock) -> None:
        """Test successful HTTP API call."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(self.sample_raw_api_data).encode(
            "utf-8"
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        data = fetch_zipcode_info("90210", "us")
        self.assertIsNotNone(data)
        self.assertEqual(data["post code"], "90210")

    def test_export_to_json(self) -> None:
        """Test exporting structured info to JSON format."""
        parsed = parse_place_details(self.sample_raw_api_data)
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp:
            tmp_name = tmp.name
        try:
            export_to_json(parsed, tmp_name)
            with open(tmp_name, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["post_code"], "90210")
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)


if __name__ == "__main__":
    unittest.main()

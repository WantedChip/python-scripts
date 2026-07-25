"""Unit tests for IP Geolocation Lookup tool."""

import json
import unittest
from unittest.mock import MagicMock, patch

from main import fetch_ip_geolocation, format_summary


class TestIPGeolocationLookup(unittest.TestCase):
    """Test suite for IP geolocation functions."""

    @patch("urllib.request.urlopen")
    def test_fetch_ip_geolocation_success(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_data = {
            "status": "success",
            "country": "United States",
            "countryCode": "US",
            "regionName": "California",
            "city": "Mountain View",
            "zip": "94043",
            "lat": 37.4056,
            "lon": -122.0775,
            "timezone": "America/Los_Angeles",
            "isp": "Google LLC",
            "query": "8.8.8.8",
        }
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = fetch_ip_geolocation("8.8.8.8")
        self.assertEqual(result["country"], "United States")
        self.assertEqual(result["city"], "Mountain View")

    @patch("urllib.request.urlopen")
    def test_fetch_ip_geolocation_fail_status(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_data = {"status": "fail", "message": "invalid query"}
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with self.assertRaises(ValueError):
            fetch_ip_geolocation("invalid-ip")

    def test_format_summary(self) -> None:
        data = {
            "query": "1.1.1.1",
            "country": "Australia",
            "countryCode": "AU",
            "city": "Sydney",
            "isp": "Cloudflare",
        }
        summary = format_summary(data)
        self.assertIn("1.1.1.1", summary)
        self.assertIn("Australia", summary)
        self.assertIn("Sydney", summary)


if __name__ == "__main__":
    unittest.main()

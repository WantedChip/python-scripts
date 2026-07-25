"""Unit tests for Country Info Fetcher."""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import (
    export_csv,
    export_json,
    fetch_country_info,
    format_country_card,
    parse_country_data,
)


class TestCountryFetcher(unittest.TestCase):
    """Test suite for country info fetcher functions."""

    def setUp(self) -> None:
        self.raw_country = {
            "name": {"common": "Japan", "official": "Japan"},
            "capital": ["Tokyo"],
            "population": 125800000,
            "region": "Asia",
            "subregion": "Eastern Asia",
            "area": 377930.0,
            "currencies": {"JPY": {"name": "Japanese yen", "symbol": "¥"}},
            "languages": {"jpn": "Japanese"},
            "flags": {"png": "https://flagcdn.com/w320/jp.png"},
            "flag": "🇯🇵",
            "maps": {"googleMaps": "https://goo.gl/maps/5t2X6qD22mB2"},
            "cca2": "JP",
        }

    def test_parse_country_data(self) -> None:
        """Test parsing raw API payload into country record."""
        parsed = parse_country_data(self.raw_country)
        self.assertEqual(parsed["common_name"], "Japan")
        self.assertEqual(parsed["capital"], "Tokyo")
        self.assertEqual(parsed["population"], 125800000)
        self.assertEqual(parsed["currencies"], "Japanese yen (¥)")
        self.assertEqual(parsed["languages"], "Japanese")
        self.assertEqual(parsed["country_code"], "JP")

    def test_format_country_card(self) -> None:
        """Test terminal country card string formatting."""
        parsed = parse_country_data(self.raw_country)
        card = format_country_card(parsed)
        self.assertIn("JAPAN", card)
        self.assertIn("Tokyo", card)
        self.assertIn("125,800,000", card)
        self.assertIn("Japanese yen (¥)", card)

    @patch("main.fetch_json")
    def test_fetch_country_info(self, mock_fetch: MagicMock) -> None:
        """Test API request for country details."""
        mock_fetch.return_value = [self.raw_country]
        results = fetch_country_info("japan")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"]["common"], "Japan")

    def test_export_json(self) -> None:
        """Test exporting country data to JSON file."""
        parsed = parse_country_data(self.raw_country)
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "country.json")
            success = export_json([parsed], file_path)
            self.assertTrue(success)
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data[0]["common_name"], "Japan")

    def test_export_csv(self) -> None:
        """Test exporting country data to CSV file."""
        parsed = parse_country_data(self.raw_country)
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "country.csv")
            success = export_csv([parsed], file_path)
            self.assertTrue(success)
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["common_name"], "Japan")


if __name__ == "__main__":
    unittest.main()

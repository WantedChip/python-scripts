"""Unit tests for University Search Fetcher."""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import (
    export_csv,
    export_json,
    extract_university_details,
    format_university_table,
    search_universities,
)


class TestUniversitySearchFetcher(unittest.TestCase):
    """Test suite for university search fetcher functions."""

    def setUp(self) -> None:
        self.raw_uni = {
            "name": "University of Toronto",
            "country": "Canada",
            "alpha_two_code": "CA",
            "state-province": "Ontario",
            "web_pages": ["http://www.utoronto.ca/"],
            "domains": ["utoronto.ca"],
        }

    def test_extract_university_details(self) -> None:
        """Test extracting formatted fields from raw university record."""
        details = extract_university_details(self.raw_uni)
        self.assertEqual(details["name"], "University of Toronto")
        self.assertEqual(details["country"], "Canada")
        self.assertEqual(details["primary_website"], "http://www.utoronto.ca/")
        self.assertEqual(details["primary_domain"], "utoronto.ca")
        self.assertEqual(details["state_province"], "Ontario")

    def test_format_university_table(self) -> None:
        """Test formatting university results into a terminal table."""
        details = extract_university_details(self.raw_uni)
        table = format_university_table([details], limit=5)
        self.assertIn("University of Toronto", table)
        self.assertIn("Canada", table)
        self.assertIn("http://www.utoronto.ca/", table)

    @patch("main.fetch_json")
    def test_search_universities(self, mock_fetch: MagicMock) -> None:
        """Test API query building for search request."""
        mock_fetch.return_value = [self.raw_uni]
        results = search_universities(country="Canada", name="Toronto")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "University of Toronto")

    def test_export_json(self) -> None:
        """Test exporting search records to JSON file."""
        details = extract_university_details(self.raw_uni)
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "unis.json")
            success = export_json([details], file_path)
            self.assertTrue(success)
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "University of Toronto")

    def test_export_csv(self) -> None:
        """Test exporting search records to CSV file."""
        details = extract_university_details(self.raw_uni)
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "unis.csv")
            success = export_csv([details], file_path)
            self.assertTrue(success)
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "University of Toronto")


if __name__ == "__main__":
    unittest.main()

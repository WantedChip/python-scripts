"""Unit tests for Country Info Fetcher."""

import csv
import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    export_csv,
    export_json,
    fetch_country_info,
    fetch_json,
    format_country_card,
    main,
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

    def test_export_json_oserror(self) -> None:
        """Unwritable JSON targets report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing" / "country.json")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = export_json([parse_country_data(self.raw_country)], bad_path)
        self.assertFalse(success)
        self.assertIn("Error exporting JSON", stderr.getvalue())

    def test_export_csv_empty_list(self) -> None:
        """Exporting an empty country list is rejected up front."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "country.csv")
            self.assertFalse(export_csv([], file_path))
            self.assertFalse(Path(file_path).exists())

    def test_export_csv_oserror(self) -> None:
        """Unwritable CSV targets report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing" / "country.csv")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = export_csv([parse_country_data(self.raw_country)], bad_path)
        self.assertFalse(success)
        self.assertIn("Error exporting CSV", stderr.getvalue())


class TestNetworkLayer(unittest.TestCase):
    """Tests for the low-level REST Countries HTTP helper."""

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_success(self, mock_urlopen: MagicMock) -> None:
        """A 200 response with valid JSON is parsed and returned."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'[{"name": {"common": "Japan"}}]'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_json("https://restcountries.com/v3.1/name/japan")
        self.assertEqual(result, [{"name": {"common": "Japan"}}])

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_non_200_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Non-200 statuses without HTTPError map to None."""
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_resp.read.return_value = b""
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("https://example.com/api"))

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_http_404_message(self, mock_urlopen: MagicMock) -> None:
        """HTTP 404 reports a country-not-found message to stderr."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://restcountries.com/v3.1/name/xyz",
            404,
            "Not Found",
            None,
            io.BytesIO(b"not found"),
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_json("https://restcountries.com/v3.1/name/xyz")
        self.assertIsNone(result)
        self.assertIn("Error 404: Country not found", stderr.getvalue())

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_other_http_error(self, mock_urlopen: MagicMock) -> None:
        """Non-404 HTTP errors report the code and reason."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com/api",
            500,
            "Internal Server Error",
            None,
            io.BytesIO(b"oops"),
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_json("https://example.com/api")
        self.assertIsNone(result)
        self.assertIn("HTTP Error 500: Internal Server Error", stderr.getvalue())

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_url_error(self, mock_urlopen: MagicMock) -> None:
        """Connection-level failures report a network error message."""
        mock_urlopen.side_effect = urllib.error.URLError("no route to host")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_json("https://example.com/api")
        self.assertIsNone(result)
        self.assertIn("Network error accessing", stderr.getvalue())


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    def setUp(self) -> None:
        self.japan = {
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
        self.canada = {
            "name": {"common": "Canada", "official": "Canada"},
            "capital": ["Ottawa"],
            "population": 38000000,
            "region": "Americas",
            "subregion": "Northern America",
            "area": 9984670.0,
            "currencies": {},
            "languages": {},
            "flags": {"png": "https://flagcdn.com/w320/ca.png"},
            "flag": "",
            "maps": {"googleMaps": "https://goo.gl/maps/canada"},
            "cca2": "CA",
        }

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

    @patch("main.fetch_country_info")
    def test_cli_single_match_prints_card(self, mock_fetch: MagicMock) -> None:
        """A single match prints the country facts card."""
        mock_fetch.return_value = [self.japan]
        stdout, _, code = self._run_cli("japan")
        self.assertIsNone(code)
        self.assertIn("COUNTRY FACTS: JAPAN", stdout)
        self.assertIn("Tokyo", stdout)

    @patch("main.fetch_country_info")
    def test_cli_multiple_matches_listing(self, mock_fetch: MagicMock) -> None:
        """Additional matches are summarized under the primary card."""
        mock_fetch.return_value = [self.japan, self.canada]
        stdout, _, code = self._run_cli("ja")
        self.assertIsNone(code)
        self.assertIn("Other matching countries (1):", stdout)
        self.assertIn("Canada (Canada) - Capital: Ottawa", stdout)

    @patch("main.fetch_country_info")
    def test_cli_parse_defaults_for_sparse_payloads(
        self, mock_fetch: MagicMock
    ) -> None:
        """Sparse payloads fall back to N/A placeholders in the card."""
        sparse = {
            "name": {},
            "currencies": {"EUR": {"name": "Euro"}},
            "languages": ["French"],
        }
        mock_fetch.return_value = [sparse]
        stdout, _, code = self._run_cli("nowhere")
        self.assertIsNone(code)
        self.assertIn("Currencies    : Euro", stdout)
        self.assertIn("Languages     : N/A", stdout)
        self.assertIn("Country Code  : N/A", stdout)

    @patch("main.fetch_country_info")
    def test_cli_no_results_exits_one(self, mock_fetch: MagicMock) -> None:
        """Unknown countries exit 1 with an error on stderr."""
        mock_fetch.return_value = []
        _, stderr, code = self._run_cli("atlantis")
        self.assertEqual(code, 1)
        self.assertIn("No results found for country 'atlantis'", stderr)

    @patch("main.fetch_country_info")
    def test_cli_exports_json_and_csv(self, mock_fetch: MagicMock) -> None:
        """--json and --csv flags write parsed records to disk."""
        mock_fetch.return_value = [self.japan]
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = str(Path(tmpdir) / "out.json")
            csv_path = str(Path(tmpdir) / "out.csv")
            stdout, _, code = self._run_cli(
                "japan", "--json", json_path, "--csv", csv_path
            )
            self.assertIsNone(code)
            self.assertIn("Exported JSON data to", stdout)
            self.assertIn("Exported CSV data to", stdout)
            data = json.loads(Path(json_path).read_text(encoding="utf-8"))
            self.assertEqual(data[0]["common_name"], "Japan")
            self.assertTrue(Path(csv_path).exists())


if __name__ == "__main__":
    unittest.main()

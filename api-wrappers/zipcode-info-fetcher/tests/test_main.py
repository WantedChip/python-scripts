"""Unit tests for zipcode-info-fetcher main module."""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    export_to_json,
    fetch_zipcode_info,
    main,
    parse_place_details,
    print_terminal_card,
)


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


class TestFetchErrorPaths(unittest.TestCase):
    """Tests for HTTP/network failure handling in fetch_zipcode_info."""

    @patch("urllib.request.urlopen")
    def test_http_404_reports_missing_postal_code(
        self, mock_urlopen: MagicMock
    ) -> None:
        """HTTP 404 reports the unknown postal code and returns None."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "http://api.zippopotam.us/us/00000",
            404,
            "Not Found",
            None,
            io.BytesIO(b"not found"),
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_zipcode_info("00000", "us")
        self.assertIsNone(result)
        self.assertIn("Postal code '00000' not found", stderr.getvalue())

    @patch("urllib.request.urlopen")
    def test_other_http_errors_report_code(self, mock_urlopen: MagicMock) -> None:
        """Non-404 HTTP errors report the status code and return None."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "http://api.zippopotam.us/us/90210",
            503,
            "Service Unavailable",
            None,
            io.BytesIO(b"down"),
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_zipcode_info("90210", "us")
        self.assertIsNone(result)
        self.assertIn("HTTP Error 503: Service Unavailable", stderr.getvalue())

    @patch("urllib.request.urlopen")
    def test_url_error_reports_network_problem(self, mock_urlopen: MagicMock) -> None:
        """Network failures report an error message and return None."""
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_zipcode_info("90210", "us")
        self.assertIsNone(result)
        self.assertIn("Network error: timed out", stderr.getvalue())

    @patch("urllib.request.urlopen")
    def test_unexpected_error_is_caught(self, mock_urlopen: MagicMock) -> None:
        """Unexpected transport exceptions are caught and reported."""
        mock_urlopen.side_effect = TimeoutError("read timed out")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_zipcode_info("90210", "us")
        self.assertIsNone(result)
        self.assertIn("Unexpected error:", stderr.getvalue())

    @patch("urllib.request.urlopen")
    def test_non_200_status_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Non-200 statuses yield None without raising."""
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.read.return_value = b"boom"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_zipcode_info("90210", "us"))

    @patch("urllib.request.urlopen")
    def test_country_code_normalized_in_url(self, mock_urlopen: MagicMock) -> None:
        """Country codes are lowercased in the request path."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"post code": "SW1A"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        fetch_zipcode_info(" SW1A ", " GB ")
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "http://api.zippopotam.us/gb/SW1A")


class TestTerminalCard(unittest.TestCase):
    """Tests for terminal card rendering."""

    def setUp(self) -> None:
        self.parsed = parse_place_details(
            {
                "post code": "90210",
                "country": "United States",
                "country abbreviation": "US",
                "places": [
                    {
                        "place name": "Beverly Hills",
                        "state": "California",
                        "state abbreviation": "CA",
                        "latitude": "34.0901",
                        "longitude": "-118.4065",
                    },
                    {
                        "place name": "Los Angeles",
                        "state": "California",
                        "state abbreviation": "CA",
                        "latitude": "34.0522",
                        "longitude": "-118.2437",
                    },
                ],
            }
        )

    def test_card_with_multiple_places(self) -> None:
        """Each place renders numbered with a separator between entries."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            print_terminal_card(self.parsed)
        out = stdout.getvalue()
        self.assertIn("POSTAL CODE INFORMATION: 90210 (US)", out)
        self.assertIn("Place #1:", out)
        self.assertIn("Beverly Hills", out)
        self.assertIn("California (CA)", out)
        self.assertIn("Lat 34.0901, Lon -118.4065", out)
        self.assertIn("Place #2:", out)
        self.assertIn("Los Angeles", out)

    def test_card_without_places(self) -> None:
        """Payloads without places print the no-data notice."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            print_terminal_card({"post_code": "0000", "places": []})
        self.assertIn("No place data available.", stdout.getvalue())

    def test_parse_place_details_empty_payload(self) -> None:
        """Empty payloads produce empty structured output."""
        parsed = parse_place_details({})
        self.assertEqual(parsed["post_code"], "")
        self.assertEqual(parsed["country"], "")
        self.assertEqual(parsed["places"], [])


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

    @patch("main.fetch_zipcode_info")
    def test_cli_success_prints_card(self, mock_fetch: MagicMock) -> None:
        """A successful lookup prints the postal code card."""
        mock_fetch.return_value = {
            "post code": "90210",
            "country": "United States",
            "country abbreviation": "US",
            "places": [
                {
                    "place name": "Beverly Hills",
                    "state": "California",
                    "state abbreviation": "CA",
                    "latitude": "34.0901",
                    "longitude": "-118.4065",
                }
            ],
        }
        stdout, _, code = self._run_cli("90210")
        self.assertIsNone(code)
        self.assertIn("POSTAL CODE INFORMATION: 90210 (US)", stdout)
        self.assertIn("Beverly Hills", stdout)

    @patch("main.fetch_zipcode_info")
    def test_cli_success_exports_json(self, mock_fetch: MagicMock) -> None:
        """-o exports the parsed record as JSON."""
        mock_fetch.return_value = {
            "post code": "M5V",
            "country": "Canada",
            "country abbreviation": "CA",
            "places": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "zip.json")
            stdout, _, code = self._run_cli("M5V", "-c", "ca", "-o", out_path)
            self.assertIsNone(code)
            self.assertIn("Exported data to", stdout)
            saved = json.loads(Path(out_path).read_text(encoding="utf-8"))
        self.assertEqual(saved["post_code"], "M5V")

    @patch("main.fetch_zipcode_info")
    def test_cli_lookup_failure_exits_one(self, mock_fetch: MagicMock) -> None:
        """Failed lookups exit 1 without printing a card."""
        mock_fetch.return_value = None
        _, _, code = self._run_cli("99999")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

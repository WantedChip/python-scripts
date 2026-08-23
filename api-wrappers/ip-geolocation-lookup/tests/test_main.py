"""Unit tests for IP Geolocation Lookup tool."""

import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import fetch_ip_geolocation, format_summary, main


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

    def test_format_summary_defaults_for_missing_fields(self) -> None:
        """Sparse payloads render N/A placeholders instead of crashing."""
        summary = format_summary({})
        self.assertIn("IP Address  : N/A", summary)
        self.assertIn("Country     : N/A (N/A)", summary)
        self.assertIn("ISP         : N/A", summary)


class TestNetworkErrorPaths(unittest.TestCase):
    """Tests for HTTP/network failure handling."""

    @patch("urllib.request.urlopen")
    def test_non_200_status_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Unexpected HTTP statuses raise RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaisesRegex(RuntimeError, "status 503"):
            fetch_ip_geolocation("8.8.8.8")

    @patch("urllib.request.urlopen")
    def test_http_error_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """HTTPError instances are wrapped as RuntimeError."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "http://ip-api.com/json/8.8.8.8",
            429,
            "Too Many Requests",
            None,
            io.BytesIO(b"rate limited"),
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP Error 429"):
            fetch_ip_geolocation("8.8.8.8")

    @patch("urllib.request.urlopen")
    def test_url_error_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Network failures are wrapped as RuntimeError."""
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        with self.assertRaisesRegex(RuntimeError, "Network error"):
            fetch_ip_geolocation("8.8.8.8")

    @patch("urllib.request.urlopen")
    def test_empty_target_queries_local_ip(self, mock_urlopen: MagicMock) -> None:
        """Empty targets request the local public IP endpoint."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"status": "success"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_ip_geolocation("")
        self.assertEqual(result, {"status": "success"})
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "http://ip-api.com/json/")
        self.assertEqual(
            request.headers.get("User-agent"), "IPGeolocationLookup/1.0 (Python)"
        )


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

    GEO_DATA = {
        "status": "success",
        "query": "8.8.8.8",
        "country": "United States",
        "countryCode": "US",
        "city": "Mountain View",
        "isp": "Google LLC",
    }

    @patch("main.fetch_ip_geolocation")
    def test_cli_formatted_summary(self, mock_fetch: MagicMock) -> None:
        """Default output renders the formatted summary card."""
        mock_fetch.return_value = dict(self.GEO_DATA)
        stdout, _, code = self._run_cli("8.8.8.8")
        self.assertIsNone(code)
        self.assertIn("IP GEOLOCATION SUMMARY", stdout)
        self.assertIn("Mountain View", stdout)

    @patch("main.fetch_ip_geolocation")
    def test_cli_raw_output_and_export(self, mock_fetch: MagicMock) -> None:
        """--raw prints JSON; -o writes it to a file."""
        mock_fetch.return_value = dict(self.GEO_DATA)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "geo.json")
            stdout, _, code = self._run_cli("8.8.8.8", "--raw", "-o", out_path)
            self.assertIsNone(code)
            self.assertIn('"query": "8.8.8.8"', stdout)
            self.assertIn("Geolocation data saved to", stdout)
            saved = json.loads(Path(out_path).read_text(encoding="utf-8"))
        self.assertEqual(saved["isp"], "Google LLC")

    @patch("main.fetch_ip_geolocation")
    def test_cli_error_exits_one(self, mock_fetch: MagicMock) -> None:
        """Lookup errors print to stderr and exit 1."""
        mock_fetch.side_effect = ValueError("API query failed: invalid query")
        _, stderr, code = self._run_cli("999.999.999.999")
        self.assertEqual(code, 1)
        self.assertIn("Error: API query failed", stderr)


if __name__ == "__main__":
    unittest.main()

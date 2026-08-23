"""Unit tests for Public Holiday Fetcher tool."""

import datetime
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
    fetch_public_holidays,
    filter_upcoming_holidays,
    format_holiday_table,
    main,
)


class TestPublicHolidayFetcher(unittest.TestCase):
    """Test suite for public holiday fetcher functions."""

    @patch("urllib.request.urlopen")
    def test_fetch_public_holidays_success(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_data = [
            {
                "date": "2026-01-01",
                "localName": "New Year's Day",
                "name": "New Year's Day",
                "countryCode": "US",
                "types": ["Public"],
            }
        ]
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        holidays = fetch_public_holidays(2026, "US")
        self.assertEqual(len(holidays), 1)
        self.assertEqual(holidays[0]["localName"], "New Year's Day")

    def test_filter_upcoming_holidays(self) -> None:
        holidays = [
            {"date": "2026-01-01", "name": "Past Holiday"},
            {"date": "2026-07-04", "name": "Independence Day"},
            {"date": "2026-12-25", "name": "Christmas Day"},
        ]
        ref_date = datetime.date(2026, 6, 1)
        upcoming = filter_upcoming_holidays(holidays, reference_date=ref_date)
        self.assertEqual(len(upcoming), 2)
        self.assertEqual(upcoming[0]["name"], "Independence Day")

    def test_format_holiday_table(self) -> None:
        holidays = [
            {
                "date": "2026-01-01",
                "localName": "Neujahr",
                "name": "New Year's Day",
                "types": ["Public"],
            }
        ]
        table = format_holiday_table(holidays, "DE", 2026)
        self.assertIn("Neujahr", table)
        self.assertIn("2026-01-01", table)

    def test_format_holiday_table_empty(self) -> None:
        """Empty holiday lists render a friendly message."""
        table = format_holiday_table([], "US", 2027)
        self.assertEqual(table, "No holidays found for US (2027).")

    def test_format_holiday_table_defaults_public_type(self) -> None:
        """Holidays without types fall back to the Public label."""
        holidays = [
            {"date": "2026-12-24", "localName": "Julafton", "name": "Christmas Eve"}
        ]
        table = format_holiday_table(holidays, "SE", 2026)
        self.assertIn("Public", table)


class TestHolidayErrorPaths(unittest.TestCase):
    """Tests for API error handling in fetch_public_holidays."""

    @patch("urllib.request.urlopen")
    def test_non_200_status_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Unexpected HTTP statuses raise RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaisesRegex(RuntimeError, "API Error 503"):
            fetch_public_holidays(2026, "US")

    @patch("urllib.request.urlopen")
    def test_http_404_maps_to_value_error(self, mock_urlopen: MagicMock) -> None:
        """HTTP 404 indicates an invalid country code or year."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://date.nager.at/api/v3/PublicHolidays/2026/ZZ",
            404,
            "Not Found",
            None,
            io.BytesIO(b"not found"),
        )
        with self.assertRaises(ValueError):
            fetch_public_holidays(2026, "zz")

    @patch("urllib.request.urlopen")
    def test_other_http_errors_raise_runtime_error(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Non-404 HTTP errors raise RuntimeError with the code."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://date.nager.at/api/v3/PublicHolidays/2026/US",
            500,
            "Internal Server Error",
            None,
            io.BytesIO(b"oops"),
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP Error 500"):
            fetch_public_holidays(2026, "US")

    @patch("urllib.request.urlopen")
    def test_url_error_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Network failures raise RuntimeError."""
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        with self.assertRaisesRegex(RuntimeError, "Network connection error"):
            fetch_public_holidays(2026, "US")


class TestFilterEdgeCases(unittest.TestCase):
    """Tests for upcoming-holiday filtering edge cases."""

    def test_invalid_dates_are_skipped(self) -> None:
        """Entries with unparseable dates are dropped silently."""
        holidays = [
            {"date": "not-a-date", "name": "Broken"},
            {"date": "2099-01-01", "name": "Far Future"},
        ]
        upcoming = filter_upcoming_holidays(
            holidays, reference_date=datetime.date(2026, 1, 1)
        )
        self.assertEqual([h["name"] for h in upcoming], ["Far Future"])

    def test_missing_date_key_is_skipped(self) -> None:
        """Entries lacking a date key are dropped silently."""
        upcoming = filter_upcoming_holidays(
            [{"name": "No date"}], reference_date=datetime.date(2026, 1, 1)
        )
        self.assertEqual(upcoming, [])

    def test_default_reference_date_is_today(self) -> None:
        """Without an explicit cutoff the filter uses today's date."""
        next_year = datetime.date.today().year + 1
        holidays = [
            {"date": f"{next_year}-06-01", "name": "Future"},
            {"date": "1999-01-01", "name": "Ancient"},
        ]
        upcoming = filter_upcoming_holidays(holidays)
        self.assertEqual([h["name"] for h in upcoming], ["Future"])


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    HOLIDAYS = [
        {
            "date": "2026-07-04",
            "localName": "Independence Day",
            "name": "Independence Day",
            "countryCode": "US",
            "types": ["Public"],
        },
        {
            "date": "2026-12-25",
            "localName": "Juldagen",
            "name": "Christmas Day",
            "countryCode": "SE",
            "types": ["Public"],
        },
    ]

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

    @patch("main.fetch_public_holidays")
    def test_cli_table_output(self, mock_fetch: MagicMock) -> None:
        """Default output renders the holiday table."""
        mock_fetch.return_value = [dict(h) for h in self.HOLIDAYS]
        stdout, _, code = self._run_cli("-c", "US", "-y", "2026")
        self.assertIsNone(code)
        self.assertIn("Public Holidays for US (2026)", stdout)
        self.assertIn("Independence Day", stdout)

    @patch("main.fetch_public_holidays")
    def test_cli_upcoming_filter_applied(self, mock_fetch: MagicMock) -> None:
        """--upcoming trims holidays before today's date."""
        mock_fetch.return_value = [dict(h) for h in self.HOLIDAYS]
        stdout, _, code = self._run_cli("--upcoming", "-c", "US", "-y", "2026")
        self.assertIsNone(code)
        self.assertIn("Total: 1", stdout)
        self.assertIn("Christmas Day", stdout)
        self.assertNotIn("Independence Day", stdout)

    @patch("main.fetch_public_holidays")
    def test_cli_json_output(self, mock_fetch: MagicMock) -> None:
        """--format json prints raw holiday records."""
        mock_fetch.return_value = [dict(h) for h in self.HOLIDAYS]
        stdout, _, code = self._run_cli("-f", "json", "-c", "US")
        self.assertIsNone(code)
        parsed = json.loads(stdout)
        self.assertEqual(parsed[0]["localName"], "Independence Day")

    @patch("main.fetch_public_holidays")
    def test_cli_output_file_json_and_txt(self, mock_fetch: MagicMock) -> None:
        """-o writes JSON for .json suffixes and text otherwise."""
        mock_fetch.return_value = [dict(h) for h in self.HOLIDAYS]
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = str(Path(tmpdir) / "holidays.json")
            txt_path = str(Path(tmpdir) / "holidays.txt")
            stdout1, _, code1 = self._run_cli("-o", json_path, "-f", "json", "-c", "US")
            stdout2, _, code2 = self._run_cli("-o", txt_path, "-c", "US")
            self.assertIsNone(code1)
            self.assertIsNone(code2)
            saved = json.loads(Path(json_path).read_text(encoding="utf-8"))
            text = Path(txt_path).read_text(encoding="utf-8")
        self.assertEqual(len(saved), 2)
        self.assertIn("Holidays saved to", stdout2)
        self.assertIn("Public Holidays for US (2026)", text)
        self.assertIn('"localName"', stdout1)

    @patch("main.fetch_public_holidays")
    def test_cli_error_exits_one(self, mock_fetch: MagicMock) -> None:
        """Fetch failures print to stderr and exit 1."""
        mock_fetch.side_effect = ValueError("Country code 'ZZ' or year not found.")
        _, stderr, code = self._run_cli("-c", "zz")
        self.assertEqual(code, 1)
        self.assertIn("Error:", stderr)


if __name__ == "__main__":
    unittest.main()

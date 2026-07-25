"""Unit tests for Public Holiday Fetcher tool."""

import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

from main import fetch_public_holidays, filter_upcoming_holidays, format_holiday_table


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


if __name__ == "__main__":
    unittest.main()

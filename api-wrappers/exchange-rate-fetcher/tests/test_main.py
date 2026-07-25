"""Unit tests for Exchange Rate Fetcher tool."""

import json
import unittest
from unittest.mock import MagicMock, patch

from main import convert_currency, fetch_exchange_rates, format_rate_table


class TestExchangeRateFetcher(unittest.TestCase):
    """Test suite for exchange rate fetcher functions."""

    @patch("urllib.request.urlopen")
    def test_fetch_exchange_rates_success(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_data = {
            "result": "success",
            "time_last_update_utc": "Fri, 24 Jul 2026 00:00:00 +0000",
            "base_code": "USD",
            "rates": {"EUR": 0.92, "GBP": 0.78, "JPY": 155.5},
        }
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        data = fetch_exchange_rates("USD")
        self.assertEqual(data["base"], "USD")
        self.assertEqual(data["rates"]["EUR"], 0.92)

    def test_convert_currency(self) -> None:
        rates_data = {"base": "USD", "rates": {"EUR": 0.90, "GBP": 0.80}}
        results = convert_currency(
            amount=100.0,
            base="USD",
            target_currencies=["EUR", "GBP"],
            rates_data=rates_data,
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["target"], "EUR")
        self.assertEqual(results[0]["converted_amount"], 90.0)

    def test_format_rate_table(self) -> None:
        conversions = [
            {
                "amount": 1.0,
                "base": "USD",
                "target": "EUR",
                "rate": 0.92,
                "converted_amount": 0.92,
            }
        ]
        table = format_rate_table(conversions, "USD", "2026-07-24")
        self.assertIn("Exchange Rates for USD", table)
        self.assertIn("EUR", table)


if __name__ == "__main__":
    unittest.main()

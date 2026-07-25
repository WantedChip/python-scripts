"""Unit tests for Bitcoin Price Fetcher."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import (
    check_price_alerts,
    fetch_coingecko_price,
    fetch_crypto_price,
    format_ticker_card,
    log_price_to_csv,
)


class TestBitcoinPriceFetcher(unittest.TestCase):
    """Test suite for crypto price fetcher functions."""

    def setUp(self) -> None:
        self.sample_coingecko = {
            "bitcoin": {
                "usd": 65000.0,
                "usd_market_cap": 1200000000000.0,
                "usd_24h_change": 2.5,
                "usd_24h_vol": 30000000000.0,
            }
        }
        self.sample_data_dict = {
            "source": "CoinGecko",
            "coin": "bitcoin",
            "currency": "USD",
            "price": 65000.0,
            "market_cap": 1200000000000.0,
            "change_24h": 2.5,
            "volume_24h": 30000000000.0,
        }

    @patch("main.fetch_json")
    def test_fetch_coingecko_price(self, mock_fetch: MagicMock) -> None:
        """Test fetching price stats from CoinGecko API."""
        mock_fetch.return_value = self.sample_coingecko
        res = fetch_coingecko_price("bitcoin", "usd")
        self.assertIsNotNone(res)
        self.assertEqual(res["price"], 65000.0)
        self.assertEqual(res["change_24h"], 2.5)

    @patch("main.fetch_coingecko_price")
    @patch("main.fetch_coindesk_bitcoin_price")
    def test_fetch_crypto_price_fallback(
        self, mock_coindesk: MagicMock, mock_coingecko: MagicMock
    ) -> None:
        """Test fallback mechanism when CoinGecko fails."""
        mock_coingecko.return_value = None
        mock_coindesk.return_value = {
            "source": "CoinDesk",
            "coin": "bitcoin",
            "currency": "USD",
            "price": 64500.0,
            "market_cap": 0.0,
            "change_24h": 0.0,
            "volume_24h": 0.0,
        }
        res = fetch_crypto_price("bitcoin", "usd")
        self.assertIsNotNone(res)
        self.assertEqual(res["source"], "CoinDesk")
        self.assertEqual(res["price"], 64500.0)

    def test_check_price_alerts(self) -> None:
        """Test high and low threshold price alert triggers."""
        # High alert triggered
        alerts_high = check_price_alerts(65000.0, alert_above=60000.0, alert_below=None)
        self.assertEqual(len(alerts_high), 1)
        self.assertIn("HIGH ALERT", alerts_high[0])

        # Low alert triggered
        alerts_low = check_price_alerts(45000.0, alert_above=None, alert_below=50000.0)
        self.assertEqual(len(alerts_low), 1)
        self.assertIn("LOW ALERT", alerts_low[0])

        # No alert
        alerts_none = check_price_alerts(
            55000.0, alert_above=60000.0, alert_below=50000.0
        )
        self.assertEqual(len(alerts_none), 0)

    def test_format_ticker_card(self) -> None:
        """Test ticker card string formatting."""
        card = format_ticker_card(self.sample_data_dict)
        self.assertIn("BITCOIN / USD", card)
        self.assertIn("$65,000.00 USD", card)
        self.assertIn("+2.50%", card)

    def test_log_price_to_csv(self) -> None:
        """Test appending price entries to CSV log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "prices.csv")
            success = log_price_to_csv(file_path, self.sample_data_dict)
            self.assertTrue(success)

            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["coin"], "bitcoin")
            self.assertEqual(float(rows[0]["price"]), 65000.0)


if __name__ == "__main__":
    unittest.main()

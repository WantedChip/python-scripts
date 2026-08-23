"""Unit tests for Bitcoin Price Fetcher."""

import csv
import io
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    check_price_alerts,
    fetch_coindesk_bitcoin_price,
    fetch_coingecko_price,
    fetch_crypto_price,
    fetch_json,
    format_ticker_card,
    log_price_to_csv,
    main,
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

    def test_log_price_to_csv_oserror(self) -> None:
        """Unwritable target paths report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing_dir" / "prices.csv")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = log_price_to_csv(bad_path, self.sample_data_dict)
        self.assertFalse(success)
        self.assertIn("Error logging to CSV file", stderr.getvalue())


class TestNetworkLayer(unittest.TestCase):
    """Tests for the low-level JSON HTTP helper."""

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_success(self, mock_urlopen: MagicMock) -> None:
        """A 200 response with valid JSON is parsed into a dictionary."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"bitcoin": {"usd": 1.0}}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_json("https://example.com/api")

        self.assertEqual(result, {"bitcoin": {"usd": 1.0}})
        request = mock_urlopen.call_args[0][0]
        self.assertIn("example.com/api", request.full_url)
        self.assertEqual(
            request.headers.get("User-agent"), "BitcoinPriceFetcher/1.0 (Python)"
        )

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_non_200_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Non-200 status codes yield None without raising."""
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_resp.read.return_value = b"unavailable"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("https://example.com/api"))

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_network_error_returns_none(
        self, mock_urlopen: MagicMock
    ) -> None:
        """URLError is reported to stderr and mapped to None."""
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_json("https://example.com/api")
        self.assertIsNone(result)
        self.assertIn("Error fetching from https://example.com/api", stderr.getvalue())

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_malformed_payload_returns_none(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Invalid JSON payloads are treated as fetch failures."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>not-json</html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("https://example.com/api"))

    @patch("main.fetch_json")
    def test_fetch_coingecko_price_unknown_coin(self, mock_fetch: MagicMock) -> None:
        """Unknown coins map to None instead of raising KeyError."""
        mock_fetch.return_value = {"litecoin": {"usd": 90.0}}
        self.assertIsNone(fetch_coingecko_price("notacoin", "usd"))


class TestCoinDeskFallback(unittest.TestCase):
    """Tests for the CoinDesk fallback price source."""

    @patch("main.fetch_json")
    def test_fetch_coindesk_bitcoin_price(self, mock_fetch: MagicMock) -> None:
        """A BPI payload is normalized into ticker statistics."""
        mock_fetch.return_value = {"bpi": {"USD": {"rate_float": 64500.0}}}
        res = fetch_coindesk_bitcoin_price()
        self.assertIsNotNone(res)
        self.assertEqual(res["source"], "CoinDesk")
        self.assertEqual(res["price"], 64500.0)
        self.assertEqual(res["currency"], "USD")

    @patch("main.fetch_json")
    def test_fetch_coindesk_missing_bpi(self, mock_fetch: MagicMock) -> None:
        """Payloads without BPI data map to None."""
        mock_fetch.return_value = {"time": "2026-01-01"}
        self.assertIsNone(fetch_coindesk_bitcoin_price())

    @patch("main.fetch_coindesk_bitcoin_price")
    @patch("main.fetch_coingecko_price")
    def test_fallback_not_used_for_non_bitcoin(
        self, mock_coingecko: MagicMock, mock_coindesk: MagicMock
    ) -> None:
        """CoinDesk fallback is skipped for non-bitcoin queries."""
        mock_coingecko.return_value = None
        res = fetch_crypto_price("ethereum", "usd")
        self.assertIsNone(res)
        mock_coindesk.assert_not_called()


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

    @patch("main.fetch_crypto_price")
    def test_cli_success_prints_ticker_and_logs_csv(
        self, mock_fetch: MagicMock
    ) -> None:
        """A successful run prints the ticker card, alerts, and logs CSV."""
        mock_fetch.return_value = {
            "source": "CoinGecko",
            "coin": "ethereum",
            "currency": "USD",
            "price": 3500.0,
            "market_cap": 420000000000.0,
            "change_24h": -1.2,
            "volume_24h": 15000000000.0,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = str(Path(tmpdir) / "log.csv")
            stdout, _, code = self._run_cli(
                "--coin",
                "ethereum",
                "--currency",
                "usd",
                "--alert-above",
                "3000",
                "--log-csv",
                csv_path,
            )
            self.assertIsNone(code)
            self.assertIn("CRYPTO TICKER: ETHEREUM / USD", stdout)
            self.assertIn("$3,500.00 USD", stdout)
            self.assertIn("-1.20%", stdout)
            self.assertIn("[ALERT] HIGH ALERT", stdout)
            self.assertTrue(Path(csv_path).exists())

    @patch("main.fetch_crypto_price")
    def test_cli_no_alerts_when_within_thresholds(self, mock_fetch: MagicMock) -> None:
        """No alert banner is printed while price sits between thresholds."""
        mock_fetch.return_value = {
            "source": "CoinGecko",
            "coin": "bitcoin",
            "currency": "USD",
            "price": 50000.0,
            "market_cap": 0.0,
            "change_24h": 0.0,
            "volume_24h": 0.0,
        }
        stdout, _, code = self._run_cli(
            "--alert-above", "60000", "--alert-below", "40000"
        )
        self.assertIsNone(code)
        self.assertNotIn("[ALERT]", stdout)
        self.assertIn("Market Cap    : N/A", stdout)

    @patch("main.fetch_crypto_price")
    def test_cli_failure_exits_nonzero(self, mock_fetch: MagicMock) -> None:
        """Missing price data exits with status 1 and an error message."""
        mock_fetch.return_value = None
        _, stderr, code = self._run_cli("--coin", "bitcoin")
        self.assertEqual(code, 1)
        self.assertIn("Could not fetch price data for coin 'bitcoin'", stderr)


if __name__ == "__main__":
    unittest.main()

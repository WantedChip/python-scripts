import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    StockQuote,
    build_parser,
    calculate_change,
    fetch_mock_quote,
    fetch_stooq_quote,
    fetch_yahoo_quote,
    get_stock_quote,
    log_quotes_to_csv,
    main,
)


def _urlopen_result(payload: Any) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = 200
    body = payload if isinstance(payload, str) else json.dumps(payload)
    resp.read.return_value = body.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


STOOQ_CSV = (
    "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
    "aapl.us,2026-08-21,22:00:00,170.0,175.5,168.2,173.25,81234567\n"
)

YAHOO_JSON = {
    "chart": {
        "result": [
            {
                "meta": {
                    "regularMarketPrice": 412.6,
                    "chartPreviousClose": 405.1,
                    "regularMarketDayHigh": 415.0,
                    "regularMarketDayLow": 403.0,
                    "regularMarketVolume": 23456789,
                }
            }
        ]
    }
}


class TestStockPriceScraper(unittest.TestCase):

    def test_calculate_change(self):
        chg, chg_pct = calculate_change(150.0, 100.0)
        self.assertEqual(chg, 50.0)
        self.assertEqual(chg_pct, 50.0)

        chg_down, chg_pct_down = calculate_change(80.0, 100.0)
        self.assertEqual(chg_down, -20.0)
        self.assertEqual(chg_pct_down, -20.0)

        chg_zero, chg_pct_zero = calculate_change(100.0, 0.0)
        self.assertEqual(chg_zero, 0.0)
        self.assertEqual(chg_pct_zero, 0.0)

    def test_mock_quote_generation(self):
        quote = fetch_mock_quote("AAPL")
        self.assertEqual(quote.ticker, "AAPL")
        self.assertGreater(quote.price, 0.0)
        self.assertGreaterEqual(quote.high, quote.low)

    def test_get_stock_quote_mock_provider(self):
        quote = get_stock_quote("MSFT", provider="mock")
        self.assertIsNotNone(quote)
        self.assertEqual(quote.ticker, "MSFT")

    def test_log_quotes_to_csv(self):
        q1 = fetch_mock_quote("AAPL")
        q2 = fetch_mock_quote("GOOGL")

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test_log.csv")
            log_quotes_to_csv([q1, q2], csv_path)

            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = list(csv.reader(f))
                self.assertEqual(len(reader), 3)  # Header + 2 rows
                header = reader[0]
                self.assertIn("ticker", header)
                self.assertIn("change_percent", header)

            # Test appending to existing file (header should not duplicate)
            log_quotes_to_csv([q1], csv_path)
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = list(csv.reader(f))
                self.assertEqual(len(reader), 4)  # 1 header + 3 rows


class TestProviderParsers(unittest.TestCase):
    """Stooq/Yahoo response parsing with mocked HTTP transports."""

    def test_stock_quote_to_dict_roundtrip(self) -> None:
        quote = fetch_mock_quote("TSLA")
        data = quote.to_dict()
        self.assertEqual(data["ticker"], "TSLA")
        self.assertEqual(
            set(data.keys()),
            {
                "ticker",
                "timestamp",
                "price",
                "open_price",
                "high",
                "low",
                "volume",
                "prev_close",
                "change",
                "change_percent",
            },
        )

    def test_fetch_stooq_quote_parses_csv_row(self) -> None:
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(STOOQ_CSV)
        ):
            quote = fetch_stooq_quote("aapl")
        assert quote is not None
        self.assertEqual(quote.ticker, "AAPL")
        self.assertEqual(quote.price, 173.25)
        self.assertEqual(quote.open_price, 170.0)
        self.assertEqual(quote.high, 175.5)
        self.assertEqual(quote.low, 168.2)
        self.assertEqual(quote.volume, 81234567)
        # prev_close falls back to open; change computed against it.
        self.assertEqual(quote.change, round(173.25 - 170.0, 4))

    def test_fetch_stooq_quote_nd_marker_returns_none(self) -> None:
        bad_csv = "Symbol,Date,Time,Open,High,Low,Close,Volume\nmsft.us,N/D,,,,,,\n"
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(bad_csv)
        ):
            self.assertIsNone(fetch_stooq_quote("MSFT"))

    def test_fetch_stooq_quote_header_only_returns_none(self) -> None:
        header_only = "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(header_only)
        ):
            self.assertIsNone(fetch_stooq_quote("MSFT"))

    def test_fetch_stooq_quote_network_error_returns_none(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            self.assertIsNone(fetch_stooq_quote("MSFT"))

    def test_fetch_yahoo_quote_parses_meta(self) -> None:
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(YAHOO_JSON)
        ):
            quote = fetch_yahoo_quote("googl")
        assert quote is not None
        self.assertEqual(quote.ticker, "GOOGL")
        self.assertEqual(quote.price, 412.6)
        self.assertEqual(quote.prev_close, 405.1)
        self.assertEqual(quote.change, round(412.6 - 405.1, 4))
        self.assertAlmostEqual(quote.change_percent, round(7.5 / 405.1 * 100.0, 4))

    def test_fetch_yahoo_quote_malformed_json_returns_none(self) -> None:
        resp = _urlopen_result("{not-json")
        with patch("main.urllib.request.urlopen", return_value=resp):
            self.assertIsNone(fetch_yahoo_quote("GOOGL"))

    def test_get_stock_quote_auto_prefers_stooq_then_falls_back(self) -> None:
        """auto tries stooq first, then yahoo, then lands on mock."""
        with patch("main.fetch_stooq_quote", return_value=None):
            with patch("main.fetch_yahoo_quote", return_value=None):
                quote = get_stock_quote("NVDA", provider="auto")
        assert quote is not None
        self.assertEqual(quote.ticker, "NVDA")

    def test_get_stock_quote_explicit_provider_skips_others(self) -> None:
        stooq_quote = fetch_mock_quote("AMD")
        yahoo_quote = fetch_mock_quote("INTC")
        with patch("main.fetch_stooq_quote", return_value=stooq_quote) as m_stooq:
            with patch("main.fetch_yahoo_quote", return_value=yahoo_quote) as m_yahoo:
                quote = get_stock_quote("AMD", provider="stooq")
        self.assertIs(quote, stooq_quote)
        m_stooq.assert_called_once()
        m_yahoo.assert_not_called()


class TestStockPriceCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def test_build_parser_requires_tickers(self) -> None:
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args([])
        args = parser.parse_args(["--tickers", "aapl, msft"])
        self.assertEqual(args.provider, "auto")
        self.assertEqual(args.csv_file, "stock_quotes_log.csv")

    def test_main_mock_provider_logs_and_summarizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "log.csv")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(
                    [
                        "--tickers",
                        "AAPL,MSFT",
                        "--provider",
                        "mock",
                        "--csv-file",
                        csv_path,
                        "--summary",
                    ]
                )
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn(f"Logged 2 quotes to {csv_path}", out)
            self.assertIn("--- Stock Quotes Summary ---", out)
            with open(csv_path, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)

    def test_main_negative_change_has_no_plus_sign(self) -> None:
        quote = StockQuote(
            ticker="XYZ",
            timestamp="2026-08-23T00:00:00+00:00",
            price=90.0,
            open_price=100.0,
            high=101.0,
            low=89.0,
            volume=10,
            prev_close=100.0,
            change=-10.0,
            change_percent=-10.0,
        )
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.get_stock_quote", return_value=quote):
                with redirect_stdout(buf):
                    code = main(
                        [
                            "--tickers",
                            "XYZ",
                            "--csv-file",
                            os.path.join(tmpdir, "x.csv"),
                            "--summary",
                        ]
                    )
        self.assertEqual(code, 0)
        self.assertIn("Change: -10.00 (-10.00%)", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

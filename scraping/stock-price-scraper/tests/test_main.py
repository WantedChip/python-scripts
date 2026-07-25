import csv
import os
import tempfile
import unittest

from main import calculate_change, fetch_mock_quote, get_stock_quote, log_quotes_to_csv


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


if __name__ == "__main__":
    unittest.main()

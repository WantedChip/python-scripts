import tempfile
import unittest
from pathlib import Path

from main import (
    extract_currency_code,
    normalize_currency_entry,
    parse_currency_amount,
    process_currency_csv,
)


class TestCurrencyNormalizer(unittest.TestCase):
    """Test suite for currency normalizer tool."""

    def test_extract_currency_code(self) -> None:
        text, code = extract_currency_code("$1,234.50")
        self.assertEqual(code, "USD")

        text, code = extract_currency_code("€1.234,50")
        self.assertEqual(code, "EUR")

        text, code = extract_currency_code("1234.5 CAD")
        self.assertEqual(code, "CAD")

    def test_parse_currency_amount(self) -> None:
        self.assertEqual(parse_currency_amount("1,234.50"), 1234.50)
        self.assertEqual(parse_currency_amount("1.234,50"), 1234.50)
        self.assertEqual(parse_currency_amount("5000"), 5000.0)
        self.assertEqual(parse_currency_amount("(500.25)"), -500.25)
        self.assertEqual(parse_currency_amount("-50.00"), -50.0)

    def test_normalize_currency_entry(self) -> None:
        amount, code, status = normalize_currency_entry("$1,234.50", "USD")
        self.assertEqual(amount, 1234.50)
        self.assertEqual(code, "USD")
        self.assertEqual(status, "SUCCESS")

        amount, code, status = normalize_currency_entry("€1.234,50", "USD")
        self.assertEqual(amount, 1234.50)
        self.assertEqual(code, "EUR")
        self.assertEqual(status, "SUCCESS")

        amount, code, status = normalize_currency_entry("invalid", "USD")
        self.assertIsNone(amount)
        self.assertEqual(status, "FAILED")

    def test_process_currency_csv(self) -> None:
        csv_content = "item,price\nItem A,$1,234.50\nItem B,€1.234,50\nItem C,invalid\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.csv"
            output_path = Path(tmpdir) / "output.csv"
            input_path.write_text(csv_content, encoding="utf-8")

            success, failed, empty = process_currency_csv(
                input_file=input_path,
                output_file=output_path,
                currency_column="price",
            )

            self.assertEqual(success, 2)
            self.assertEqual(failed, 1)
            self.assertTrue(output_path.exists())

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("1234.50", content)
            self.assertIn("USD", content)
            self.assertIn("EUR", content)


if __name__ == "__main__":
    unittest.main()

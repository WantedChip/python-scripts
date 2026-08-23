import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import List

from main import (
    extract_currency_code,
    main,
    normalize_currency_entry,
    parse_args,
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
        csv_content = (
            "item,price\n"
            'Item A,"$1,234.50"\n'
            'Item B,"€1.234,50"\n'
            "Item C,invalid\n"
        )
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


class TestProcessCurrencyCsvErrors(unittest.TestCase):
    """Error handling and lookup rules of process_currency_csv."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.output_path = self.dir_path / "out.csv"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_input(self, content: str) -> Path:
        """Write CSV content into the temp dir and return its path."""
        input_path = self.dir_path / "in.csv"
        input_path.write_text(content, encoding="utf-8")
        return input_path

    def _read_output_rows(self, output: Path) -> List[List[str]]:
        """Read all rows from a CSV file."""
        with open(output, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    def test_missing_input_file_raises(self) -> None:
        """A nonexistent input path raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            process_currency_csv(
                input_file=self.dir_path / "missing.csv",
                output_file=self.output_path,
                currency_column="price",
            )

    def test_empty_input_csv_raises(self) -> None:
        """A headerless (empty) input CSV raises ValueError."""
        input_path = self._write_input("")
        with self.assertRaises(ValueError):
            process_currency_csv(
                input_file=input_path,
                output_file=self.output_path,
                currency_column="price",
            )

    def test_unknown_column_raises(self) -> None:
        """Requesting an absent column raises ValueError."""
        input_path = self._write_input("item,price\nA,$1\n")
        with self.assertRaises(ValueError):
            process_currency_csv(
                input_file=input_path,
                output_file=self.output_path,
                currency_column="amount",
            )

    def test_numeric_column_position(self) -> None:
        """A digit string selects the column by 0-indexed position."""
        input_path = self._write_input('item,price\nA,"$5"\n')
        success, failed, empty = process_currency_csv(
            input_file=input_path,
            output_file=self.output_path,
            currency_column="1",
        )
        self.assertEqual((success, failed, empty), (1, 0, 0))
        rows = self._read_output_rows(self.output_path)
        self.assertEqual(rows[1][2], "5.00")

    def test_case_insensitive_header_match(self) -> None:
        """Column lookup ignores case differences in the header."""
        input_path = self._write_input("Item,PRICE\nA,$2\n")
        success, _, _ = process_currency_csv(
            input_file=input_path,
            output_file=self.output_path,
            currency_column="price",
        )
        self.assertEqual(success, 1)

    def test_short_rows_are_padded(self) -> None:
        """Rows shorter than the header are padded before extension."""
        input_path = self._write_input('item,price\nA,"$3"\nB,"\u20ac1",extra\n')
        process_currency_csv(
            input_file=input_path,
            output_file=self.output_path,
            currency_column="price",
        )
        rows = self._read_output_rows(self.output_path)
        self.assertEqual(rows[1], ["A", "$3", "3.00", "USD", "SUCCESS"])
        self.assertEqual(rows[2], ["B", "\u20ac1", "extra", "1.00", "EUR", "SUCCESS"])

    def test_blank_rows_skipped(self) -> None:
        """Fully blank lines are dropped instead of crashing normalization."""
        input_path = self._write_input('item,price\nA,"$1"\n\n')
        success, failed, empty = process_currency_csv(
            input_file=input_path,
            output_file=self.output_path,
            currency_column="price",
        )
        self.assertEqual((success, failed, empty), (1, 0, 0))


class TestCurrencyNormalizerEdgeCases(unittest.TestCase):
    """Additional parsing edge cases for the normalizer helpers."""

    def test_parse_currency_amount_rejects_garbage_and_blank(self) -> None:
        """Blank or non-numeric values yield None instead of raising."""
        self.assertIsNone(parse_currency_amount(""))
        self.assertIsNone(parse_currency_amount("   "))
        self.assertIsNone(parse_currency_amount("no digits here"))

    def test_parse_currency_amount_space_thousands_separator(self) -> None:
        """Space separated thousands (French style) parse correctly."""
        self.assertEqual(parse_currency_amount("1 234,50"), 1234.50)

    def test_parse_currency_amount_comma_thousands(self) -> None:
        """Comma groups with no decimal part drop the separator."""
        self.assertEqual(parse_currency_amount("1,234"), 1234.0)

    def test_parse_currency_amount_dash_variants_negative(self) -> None:
        """Unicode dash prefixes are treated as negative signs."""
        self.assertEqual(parse_currency_amount("\u201350.00"), -50.0)
        self.assertEqual(parse_currency_amount("\u20147"), -7.0)

    def test_extract_currency_code_multi_char_symbol(self) -> None:
        """Multi-character symbols like C$ map before single-char ones."""
        text, code = extract_currency_code("C$100")
        self.assertEqual(text, "100")
        self.assertEqual(code, "CAD")

    def test_extract_currency_code_falls_back_to_default(self) -> None:
        """Strings without any symbol/code use the configured fallback."""
        text, code = extract_currency_code("42")
        self.assertEqual(text, "42")
        self.assertEqual(code, "USD")

        text, code = extract_currency_code("42", default_currency="jpy")
        self.assertEqual(code, "JPY")

    def test_extract_currency_code_strips_iso_code_case_insensitive(self) -> None:
        """Lowercase ISO codes are removed and reported uppercase."""
        text, code = extract_currency_code("usd 5")
        self.assertEqual(text, "5")
        self.assertEqual(code, "USD")

    def test_normalize_currency_entry_empty_status(self) -> None:
        """Empty or whitespace-only entries report EMPTY with default code."""
        amount, code, status = normalize_currency_entry("", default_currency="gbp")
        self.assertIsNone(amount)
        self.assertEqual(code, "GBP")
        self.assertEqual(status, "EMPTY")

        _, _, status = normalize_currency_entry("   ")
        self.assertEqual(status, "EMPTY")


class TestCurrencyNormalizerCli(unittest.TestCase):
    """CLI-level tests covering argument parsing and main()."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.input_path = self.dir_path / "in.csv"
        self.output_path = self.dir_path / "out.csv"
        self.input_path.write_text(
            'item,price\nWidget,"$12.5"\nGadget,broken\nEmpty,\n',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _read_output_rows(self) -> List[List[str]]:
        """Read all rows from the CLI output CSV."""
        with open(self.output_path, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    def test_parse_args_defaults(self) -> None:
        """parse_args exposes the documented defaults."""
        args = parse_args(["-i", "a.csv", "-o", "b.csv", "-c", "price"])
        self.assertEqual(args.default_currency, "USD")
        self.assertEqual(args.input_file, Path("a.csv"))
        self.assertEqual(args.column, "price")

    def test_main_success_reports_counts(self) -> None:
        """Successful runs print a summary and write the enriched CSV."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "-i",
                    str(self.input_path),
                    "-o",
                    str(self.output_path),
                    "-c",
                    "price",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Successfully normalized: 1", output)
        self.assertIn("Failed entries: 1", output)
        self.assertIn("Empty entries: 1", output)
        rows = self._read_output_rows()
        self.assertEqual(rows[1], ["Widget", "$12.5", "12.50", "USD", "SUCCESS"])
        self.assertIn("FAILED", rows[2])
        self.assertIn("EMPTY", rows[3])

    def test_main_missing_input_returns_error_code(self) -> None:
        """main() returns 1 when the input file does not exist."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "-i",
                    str(self.dir_path / "missing.csv"),
                    "-o",
                    str(self.output_path),
                    "-c",
                    "price",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("Error:", stderr.getvalue())

    def test_main_unknown_column_returns_error_code(self) -> None:
        """main() returns 1 when the target column is absent."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "-i",
                    str(self.input_path),
                    "-o",
                    str(self.output_path),
                    "-c",
                    "nonexistent",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("not found", stderr.getvalue())

    def test_main_custom_default_currency(self) -> None:
        """--default-currency overrides the USD fallback."""
        plain = self.dir_path / "plain.csv"
        plain.write_text("item,price\nThing,99\n", encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            exit_code = main(
                [
                    "-i",
                    str(plain),
                    "-o",
                    str(self.output_path),
                    "-c",
                    "price",
                    "--default-currency",
                    "chf",
                ]
            )

        self.assertEqual(exit_code, 0)
        rows = self._read_output_rows()
        self.assertEqual(rows[1][2:], ["99.00", "CHF", "SUCCESS"])


if __name__ == "__main__":
    unittest.main()

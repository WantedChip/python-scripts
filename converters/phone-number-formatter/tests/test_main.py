import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import List

from main import (
    extract_phone_components,
    main,
    normalize_country_code,
    parse_args,
    process_csv_file,
    validate_and_format_phone,
)


class TestPhoneNumberFormatter(unittest.TestCase):
    """Test suite for phone number formatter logic."""

    def test_normalize_country_code(self) -> None:
        self.assertEqual(normalize_country_code("US"), "1")
        self.assertEqual(normalize_country_code("UK"), "44")
        self.assertEqual(normalize_country_code("+91"), "91")
        self.assertEqual(normalize_country_code("49"), "49")

    def test_extract_phone_components(self) -> None:
        cleaned, ext = extract_phone_components(" (415) 555-2671 ext 102 ")
        self.assertEqual(cleaned, "4155552671")
        self.assertEqual(ext, "102")

        cleaned, ext = extract_phone_components("+44 20 7946 0958")
        self.assertEqual(cleaned, "+442079460958")
        self.assertIsNone(ext)

    def test_validate_and_format_phone_e164(self) -> None:
        formatted, status, ext = validate_and_format_phone("4155552671", "US", "e164")
        self.assertEqual(formatted, "+14155552671")
        self.assertEqual(status, "VALID")

        formatted, status, ext = validate_and_format_phone(
            "+442079460958", "UK", "e164"
        )
        self.assertEqual(formatted, "+442079460958")
        self.assertEqual(status, "VALID")

    def test_validate_and_format_phone_national(self) -> None:
        formatted, status, ext = validate_and_format_phone(
            "4155552671", "US", "national"
        )
        self.assertEqual(formatted, "(415) 555-2671")
        self.assertEqual(status, "VALID")

    def test_validate_and_format_invalid(self) -> None:
        formatted, status, ext = validate_and_format_phone("123", "US", "e164")
        self.assertEqual(status, "INVALID")

        formatted, status, ext = validate_and_format_phone("", "US", "e164")
        self.assertEqual(status, "EMPTY")

    def test_process_csv_file(self) -> None:
        csv_content = "name,phone\nAlice,4155552671\nBob,invalid_phone\nCharlie,\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.csv"
            output_path = Path(tmpdir) / "output.csv"
            input_path.write_text(csv_content, encoding="utf-8")

            valid, invalid, empty = process_csv_file(
                input_file=input_path,
                output_file=output_path,
                phone_column="phone",
                default_country="US",
                target_format="e164",
            )

            self.assertEqual(valid, 1)
            self.assertEqual(invalid, 1)
            self.assertEqual(empty, 1)
            self.assertTrue(output_path.exists())

            output_text = output_path.read_text(encoding="utf-8")
            self.assertIn("+14155552671", output_text)
            self.assertIn("VALID", output_text)
            self.assertIn("INVALID", output_text)
            self.assertIn("EMPTY", output_text)


class TestPhoneFormattingModes(unittest.TestCase):
    """Target-format and country handling of validate_and_format_phone."""

    def test_unknown_country_falls_back_to_nanp(self) -> None:
        """Unrecognized country identifiers default to call code 1."""
        self.assertEqual(normalize_country_code("ZZ"), "1")
        self.assertEqual(normalize_country_code(""), "1")

    def test_trunk_prefix_stripped_for_non_nanp(self) -> None:
        """Leading 0 is removed when the default country is not NANP."""
        formatted, status, _ = validate_and_format_phone(
            "020 7946 0958", default_country_code="44"
        )
        self.assertEqual(formatted, "+442079460958")
        self.assertEqual(status, "VALID")

    def test_digits_only_format(self) -> None:
        """digits_only returns bare digits including country code."""
        formatted, status, _ = validate_and_format_phone(
            "4155552671", "1", "digits_only"
        )
        self.assertEqual(formatted, "14155552671")
        self.assertEqual(status, "VALID")

    def test_international_format_nanp(self) -> None:
        """international renders NANP numbers as +1 AAA-PPP-LLLL."""
        formatted, status, _ = validate_and_format_phone(
            "(415) 555-2671", "US", "international"
        )
        self.assertEqual(formatted, "+1 415-555-2671")
        self.assertEqual(status, "VALID")

    def test_international_format_other_countries_uses_e164(self) -> None:
        """Non-NANP numbers fall back to E.164 in international mode."""
        formatted, status, _ = validate_and_format_phone(
            "+493081111111", "DE", "international"
        )
        self.assertEqual(formatted, "+493081111111")
        self.assertEqual(status, "VALID")

    def test_national_format_non_nanp_returns_digits(self) -> None:
        """national keeps plain digits for non-NANP country codes."""
        formatted, status, _ = validate_and_format_phone(
            "+442079460958", "GB", "national"
        )
        self.assertEqual(formatted, "442079460958")
        self.assertEqual(status, "VALID")

    def test_extension_appended_to_valid_number(self) -> None:
        """Valid numbers keep their extension after formatting."""
        formatted, status, ext = validate_and_format_phone(
            "4155552671 x102", "US", "e164"
        )
        self.assertEqual(ext, "102")
        self.assertEqual(formatted, "+14155552671")
        self.assertEqual(status, "VALID")

    def test_double_zero_prefix_becomes_plus(self) -> None:
        """00 international prefixes are normalized to a leading plus."""
        cleaned, ext = extract_phone_components("0044 20 7946 0958")
        self.assertEqual(cleaned, "+442079460958")
        self.assertIsNone(ext)

    def test_whitespace_only_input_is_empty(self) -> None:
        """Whitespace-only values report EMPTY like blank ones."""
        _, status, _ = validate_and_format_phone("   ")
        self.assertEqual(status, "EMPTY")


class TestProcessCsvFileRules(unittest.TestCase):
    """Column resolution and row handling of process_csv_file."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_csv(self, content: str) -> Path:
        """Write CSV text to the temp dir and return its path."""
        path = self.dir_path / "in.csv"
        path.write_text(content, encoding="utf-8")
        return path

    def _read_rows(self, output: Path) -> List[List[str]]:
        """Read all rows from a CSV file."""
        with open(output, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    def test_missing_input_raises_file_not_found(self) -> None:
        """A nonexistent input raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            process_csv_file(
                input_file=self.dir_path / "missing.csv",
                output_file=self.dir_path / "out.csv",
                phone_column="phone",
            )

    def test_empty_input_raises_value_error(self) -> None:
        """A headerless CSV raises ValueError."""
        src = self._write_csv("")
        with self.assertRaises(ValueError):
            process_csv_file(
                input_file=src,
                output_file=self.dir_path / "out.csv",
                phone_column="phone",
            )

    def test_unknown_column_raises_value_error(self) -> None:
        """An absent phone column raises ValueError."""
        src = self._write_csv("name,tel\nA,4155552671\n")
        with self.assertRaises(ValueError):
            process_csv_file(
                input_file=src,
                output_file=self.dir_path / "out.csv",
                phone_column="phone",
            )

    def test_numeric_column_index(self) -> None:
        """Digit column specs select by 0-indexed position."""
        src = self._write_csv("name,number\nA,4155552671\n")
        out = self.dir_path / "out.csv"
        valid, invalid, empty = process_csv_file(
            input_file=src, output_file=out, phone_column="1"
        )
        self.assertEqual((valid, invalid, empty), (1, 0, 0))
        rows = self._read_rows(out)
        self.assertEqual(rows[0], ["name", "number", "formatted_phone", "phone_status"])
        self.assertEqual(rows[1][2], "+14155552671")

    def test_case_insensitive_header_lookup(self) -> None:
        """Header lookup ignores case differences."""
        src = self._write_csv("Name,PHONE\nA,4155552671\n")
        out = self.dir_path / "out.csv"
        valid, _, _ = process_csv_file(
            input_file=src, output_file=out, phone_column="phone"
        )
        self.assertEqual(valid, 1)

    def test_extension_rendered_in_output(self) -> None:
        """Extensions are appended as 'ext. N' for valid rows."""
        src = self._write_csv("phone\n4155552671 ext 55\n")
        out = self.dir_path / "out.csv"
        valid, _, _ = process_csv_file(
            input_file=src, output_file=out, phone_column="phone"
        )
        self.assertEqual(valid, 1)
        rows = self._read_rows(out)
        self.assertEqual(rows[1][1], "+14155552671 ext. 55")

    def test_short_row_padded_before_status_columns(self) -> None:
        """Rows shorter than the header are padded before appending."""
        src = self._write_csv('name,phone\nAlice,"4155552671"\nBob,"2125551212"\n')
        out = self.dir_path / "out.csv"
        valid, invalid, empty = process_csv_file(
            input_file=src, output_file=out, phone_column="phone"
        )
        self.assertEqual((valid, invalid, empty), (2, 0, 0))
        rows = self._read_rows(out)
        self.assertEqual(len(rows[1]), len(rows[2]))
        self.assertEqual(rows[2][2], "+12125551212")


class TestPhoneNumberFormatterCli(unittest.TestCase):
    """CLI-level tests covering parse_args and main()."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.input_path = self.dir_path / "contacts.csv"
        self.output_path = self.dir_path / "formatted.csv"
        self.input_path.write_text(
            "name,cell\nDana,4155552671\nEli,bad-number\nFay,\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_args_defaults(self) -> None:
        """Documented defaults are applied to optional flags."""
        args = parse_args(["-i", "a.csv", "-o", "b.csv", "-c", "phone"])
        self.assertEqual(args.default_country, "US")
        self.assertEqual(args.format, "e164")
        self.assertEqual(args.output_column, "formatted_phone")
        self.assertEqual(args.status_column, "phone_status")

    def test_main_success_prints_counts(self) -> None:
        """Successful runs print per-status counts and write output."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "-i",
                    str(self.input_path),
                    "-o",
                    str(self.output_path),
                    "-c",
                    "cell",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Valid numbers: 1", output)
        self.assertIn("Invalid numbers: 1", output)
        self.assertIn("Empty entries: 1", output)
        content = self.output_path.read_text(encoding="utf-8")
        self.assertIn("+14155552671", content)

    def test_main_national_format_flag(self) -> None:
        """--format national drives display formatting end-to-end."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "-i",
                    str(self.input_path),
                    "-o",
                    str(self.output_path),
                    "-c",
                    "cell",
                    "--format",
                    "national",
                ]
            )

        self.assertEqual(exit_code, 0)
        content = self.output_path.read_text(encoding="utf-8")
        self.assertIn("(415) 555-2671", content)

    def test_main_missing_input_returns_error(self) -> None:
        """main() returns 1 for nonexistent inputs via stderr."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "-i",
                    str(self.dir_path / "missing.csv"),
                    "-o",
                    str(self.output_path),
                    "-c",
                    "cell",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("Error:", stderr.getvalue())

    def test_main_unknown_column_returns_error(self) -> None:
        """main() returns 1 when the column cannot be resolved."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "-i",
                    str(self.input_path),
                    "-o",
                    str(self.output_path),
                    "-c",
                    "nope",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

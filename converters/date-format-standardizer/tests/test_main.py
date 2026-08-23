"""
Unit tests for date format standardizer tool.
"""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from main import main, parse_args, parse_date_string, standardize_csv_dates


class TestDateFormatStandardizer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.input_csv = Path(self.temp_dir.name) / "input.csv"
        self.output_csv = Path(self.temp_dir.name) / "output.csv"

        with open(self.input_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "created_at", "updated_at"])
            writer.writerow(["1", "01/15/2024", "Jan 16 2024"])
            writer.writerow(["2", "2024-02-20", "20th March 2024"])
            writer.writerow(["3", "15/03/2024", "invalid_date_string"])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_date_string_varied_formats(self):
        self.assertEqual(parse_date_string("01/15/2024"), "2024-01-15")
        self.assertEqual(parse_date_string("Jan 16 2024"), "2024-01-16")
        self.assertEqual(parse_date_string("2024-02-20"), "2024-02-20")
        self.assertEqual(parse_date_string("20th March 2024"), "2024-03-20")

    def test_parse_date_string_day_first(self):
        # 05/04/2024 could be May 4 (US) or April 5 (EU)
        self.assertEqual(parse_date_string("05/04/2024", day_first=False), "2024-05-04")
        self.assertEqual(parse_date_string("05/04/2024", day_first=True), "2024-04-05")

    def test_parse_date_string_invalid(self):
        self.assertIsNone(parse_date_string("not_a_date"))
        self.assertIsNone(parse_date_string(""))

    def test_standardize_csv_dates_keep_fallback(self):
        stats = standardize_csv_dates(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            target_columns=["created_at", "updated_at"],
            fallback_strategy="keep",
        )

        self.assertEqual(stats["total_rows"], 3)
        self.assertEqual(stats["failed_parses"], 1)

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(rows[0]["created_at"], "2024-01-15")
            self.assertEqual(rows[0]["updated_at"], "2024-01-16")
            self.assertEqual(rows[1]["updated_at"], "2024-03-20")
            # Unparseable fallback keep check
            self.assertEqual(rows[2]["updated_at"], "invalid_date_string")

    def test_standardize_csv_dates_null_fallback(self):
        standardize_csv_dates(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            target_columns=["updated_at"],
            fallback_strategy="null",
        )

        with open(self.output_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(rows[2]["updated_at"], "")


class TestDateFormatStandardizerAdvanced(unittest.TestCase):
    """Timestamp, timezone and fallback behaviour of the parser."""

    def test_parse_unix_timestamp_seconds(self) -> None:
        """10-digit Unix timestamps convert to UTC ISO dates."""
        self.assertEqual(parse_date_string("1700000000"), "2023-11-14")

    def test_parse_unix_timestamp_millis(self) -> None:
        """13-digit millisecond Unix timestamps convert to UTC ISO dates."""
        self.assertEqual(parse_date_string("1700000000000"), "2023-11-14")

    def test_parse_unix_timestamp_with_time(self) -> None:
        """include_time renders the full UTC timestamp for epoch inputs."""
        result = parse_date_string("1700000000", include_time=True)
        self.assertEqual(result, "2023-11-14T22:13:20Z")

    def test_parse_offset_converted_to_utc(self) -> None:
        """to_utc shifts tz-aware values to Z-suffixed UTC time."""
        result = parse_date_string(
            "2024-01-15T10:30:00+0530", to_utc=True, include_time=True
        )
        self.assertEqual(result, "2024-01-15T05:00:00Z")

    def test_parse_aware_value_without_utc_flag_keeps_instant(self) -> None:
        """Without to_utc an aware value still formats with the Z suffix."""
        result = parse_date_string("2024-01-15T10:30:00+0000")
        self.assertEqual(result, "2024-01-15T10:30:00Z")


class TestStandardizeCsvDatesOptions(unittest.TestCase):
    """Column validation, custom fallbacks and stdout rendering."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.input_csv = self.dir_path / "in.csv"
        self.output_csv = self.dir_path / "out.csv"
        with open(self.input_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "when"])
            writer.writerow(["1", "03/04/2024"])
            writer.writerow(["2", "garbage"])

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_missing_target_column_raises(self) -> None:
        """Requesting a column absent from the header raises ValueError."""
        with self.assertRaises(ValueError):
            standardize_csv_dates(
                input_file=str(self.input_csv),
                output_file=str(self.output_csv),
                target_columns=["nope"],
            )

    def test_custom_fallback_replaces_unparseable(self) -> None:
        """fallback_strategy='custom' writes the configured sentinel."""
        standardize_csv_dates(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            target_columns=["when"],
            fallback_strategy="custom",
            custom_fallback="UNKNOWN",
        )
        with open(self.output_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[1]["when"], "UNKNOWN")

    def test_stdout_output_when_no_file_given(self) -> None:
        """output_file=None streams the standardized CSV to stdout."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            stats = standardize_csv_dates(
                input_file=str(self.input_csv),
                output_file=None,
                target_columns=["when"],
            )

        self.assertEqual(stats["total_rows"], 2)
        text = stdout.getvalue()
        self.assertIn("id,when", text.replace("\r\n", "\n"))
        self.assertIn("2024-03-04", text)

    def test_day_first_applied_via_pipeline(self) -> None:
        """day_first=True disambiguates slash dates inside CSV processing."""
        standardize_csv_dates(
            input_file=str(self.input_csv),
            output_file=str(self.output_csv),
            target_columns=["when"],
            day_first=True,
        )
        with open(self.output_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["when"], "2024-04-03")


class TestDateFormatStandardizerCli(unittest.TestCase):
    """CLI-level tests for parse_args and main()."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.input_csv = self.dir_path / "events.csv"
        self.output_csv = self.dir_path / "out.csv"
        with open(self.input_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["created_at"])
            writer.writerow(["Jan 5 2024"])

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_args_defaults_and_flags(self) -> None:
        """Flag defaults are off; choices restrict --fallback values."""
        args = parse_args(["-i", "a.csv", "-c", "d1,d2"])
        self.assertEqual(args.columns, "d1,d2")
        self.assertIsNone(args.output)
        self.assertFalse(args.day_first)
        self.assertFalse(args.to_utc)
        self.assertFalse(args.include_time)
        self.assertEqual(args.fallback, "keep")
        self.assertEqual(args.custom_fallback, "")
        self.assertEqual(args.delimiter, ",")

    def test_main_success_writes_report_and_file(self) -> None:
        """A successful run prints the report and standardized file."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "-i",
                    str(self.input_csv),
                    "-o",
                    str(self.output_csv),
                    "-c",
                    "created_at",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Date Standardization Report", output)
        self.assertIn("Successfully parsed  : 1", output)
        with open(self.output_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["created_at"], "2024-01-05")

    def test_main_stdout_mode_prints_csv(self) -> None:
        """Without -o the standardized CSV goes to stdout."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["-i", str(self.input_csv), "-c", "created_at"])

        self.assertEqual(exit_code, 0)
        self.assertIn("2024-01-05", stdout.getvalue())

    def test_main_error_missing_column(self) -> None:
        """Unknown target columns make main() return 1 via stderr."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                ["-i", str(self.input_csv), "-o", str(self.output_csv), "-c", "nope"]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("Error standardizing CSV dates", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

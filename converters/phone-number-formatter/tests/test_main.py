import tempfile
import unittest
from pathlib import Path

from main import (
    extract_phone_components,
    normalize_country_code,
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


if __name__ == "__main__":
    unittest.main()

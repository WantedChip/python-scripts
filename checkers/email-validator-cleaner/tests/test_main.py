"""Unit tests for email-validator-cleaner main.py."""

import tempfile
import unittest
from pathlib import Path

from main import (
    DEFAULT_DISPOSABLE_DOMAINS,
    is_disposable_domain,
    is_valid_syntax,
    process_email_csv,
    validate_email_entry,
)


class TestEmailValidatorCleaner(unittest.TestCase):
    """Test suite for email validator and cleaner."""

    def test_is_valid_syntax(self) -> None:
        self.assertTrue(is_valid_syntax("user@example.com"))
        self.assertTrue(is_valid_syntax("user.name+tag@sub.domain.org"))
        self.assertFalse(is_valid_syntax("invalid-email"))
        self.assertFalse(is_valid_syntax("@domain.com"))
        self.assertFalse(is_valid_syntax("user@.com"))

    def test_is_disposable_domain(self) -> None:
        disp_doms = DEFAULT_DISPOSABLE_DOMAINS
        self.assertTrue(is_disposable_domain("test@mailinator.com", disp_doms))
        self.assertFalse(is_disposable_domain("test@gmail.com", disp_doms))

    def test_validate_email_entry(self) -> None:
        disp_doms = DEFAULT_DISPOSABLE_DOMAINS
        email, status = validate_email_entry("user@example.com", disp_doms)
        self.assertEqual(email, "user@example.com")
        self.assertEqual(status, "VALID")

        email, status = validate_email_entry("user@mailinator.com", disp_doms)
        self.assertEqual(status, "DISPOSABLE")

        seen = {"user@example.com"}
        email, status = validate_email_entry(
            "user@example.com", DEFAULT_DISPOSABLE_DOMAINS, seen_emails=seen
        )
        self.assertEqual(status, "DUPLICATE")

    def test_process_email_csv(self) -> None:
        csv_content = (
            "id,email\n"
            "1,valid@example.com\n"
            "2,invalid-syntax\n"
            "3,spam@mailinator.com\n"
            "4,valid@example.com\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.csv"
            output_path = Path(tmpdir) / "output.csv"
            flagged_path = Path(tmpdir) / "flagged.csv"
            input_path.write_text(csv_content, encoding="utf-8")

            stats = process_email_csv(
                input_file=input_path,
                output_file=output_path,
                email_column="email",
                check_mx=False,
                dedupe=True,
                output_flagged=flagged_path,
            )

            self.assertEqual(stats["VALID"], 1)
            self.assertEqual(stats["INVALID_SYNTAX"], 1)
            self.assertEqual(stats["DISPOSABLE"], 1)
            self.assertEqual(stats["DUPLICATE"], 1)

            self.assertTrue(output_path.exists())
            self.assertTrue(flagged_path.exists())


if __name__ == "__main__":
    unittest.main()

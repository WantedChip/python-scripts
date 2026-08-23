"""Unit tests for email-validator-cleaner main.py."""

import contextlib
import io
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main as main_module
from main import (
    DEFAULT_DISPOSABLE_DOMAINS,
    check_domain_dns,
    is_disposable_domain,
    is_valid_syntax,
    load_disposable_domains,
    parse_args,
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


class TestDisposableDomainLoading(unittest.TestCase):
    """Tests for the disposable-domain list loader."""

    def test_custom_file_extends_defaults(self) -> None:
        """Custom domain files add entries and ignore comments/blanks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dom_file = Path(tmpdir) / "disposable.txt"
            dom_file.write_text(
                "# comment line\nmailinator.com\nCustom.org\n\n",
                encoding="utf-8",
            )
            domains = load_disposable_domains(dom_file)
        self.assertIn("mailinator.com", domains)
        self.assertIn("custom.org", domains)
        self.assertTrue(domains.issuperset(DEFAULT_DISPOSABLE_DOMAINS))

    def test_missing_file_returns_defaults(self) -> None:
        """A non-existent custom file falls back to built-in defaults."""
        domains = load_disposable_domains(Path("Z:/nope/domains.txt"))
        self.assertEqual(domains, DEFAULT_DISPOSABLE_DOMAINS)


class TestValidationEdgeCases(unittest.TestCase):
    """Tests for syntax, disposable, and MX validation edge cases."""

    def test_overlength_email_rejected(self) -> None:
        """Emails longer than 254 characters fail syntax validation."""
        long_email = "a" * 250 + "@example.com"
        self.assertFalse(is_valid_syntax(long_email))

    def test_empty_email_rejected(self) -> None:
        """Empty strings fail syntax validation."""
        self.assertFalse(is_valid_syntax(""))

    def test_disposable_check_without_at_sign(self) -> None:
        """Strings without '@' are never disposable."""
        self.assertFalse(is_disposable_domain("plain-text", {"example.com"}))

    def test_blank_entry_returns_empty_status(self) -> None:
        """Whitespace-only entries are tagged EMPTY."""
        email, status = validate_email_entry("   ", set())
        self.assertEqual((email, status), ("", "EMPTY"))

    @mock.patch("socket.getaddrinfo", return_value=[("ok",)])
    def test_mx_check_success(self, _mock_dns: mock.Mock) -> None:
        """A resolvable domain passes the MX check and is VALID."""
        _, status = validate_email_entry("user@gmail.com", set(), check_mx=True)
        self.assertEqual(status, "VALID")

    @mock.patch(
        "socket.getaddrinfo", side_effect=socket.gaierror(1, "Name resolution failed")
    )
    def test_mx_check_failure(self, _mock_dns: mock.Mock) -> None:
        """An unresolvable domain is tagged MX_FAILED."""
        clean, status = validate_email_entry(
            "user@nonexistent.invalid", set(), check_mx=True
        )
        self.assertEqual(status, "MX_FAILED")
        self.assertEqual(clean, "user@nonexistent.invalid")

    def test_duplicate_without_dedupe_set_stays_valid(self) -> None:
        """Without a seen-set, repeated emails remain VALID."""
        _, status = validate_email_entry("user@example.com", set(), check_mx=False)
        self.assertEqual(status, "VALID")


class TestDomainDns(unittest.TestCase):
    """Tests for DNS resolution helper (network fully mocked)."""

    @mock.patch("socket.getaddrinfo", return_value=[("ok",)])
    def test_resolvable_domain_returns_true(self, mock_dns: mock.Mock) -> None:
        """A successful lookup returns True."""
        self.assertTrue(check_domain_dns("gmail.com"))
        mock_dns.assert_called_once()

    @mock.patch("socket.getaddrinfo", side_effect=socket.herror(1, "not found"))
    def test_unresolvable_domain_returns_false(self, _mock_dns: mock.Mock) -> None:
        """Resolution failures return False instead of raising."""
        self.assertFalse(check_domain_dns("nope.invalid"))


class TestProcessCsvPaths(unittest.TestCase):
    """Tests for CSV processing error paths and output modes."""

    def _write_csv(self, dir_path: Path, content: str, name: str = "in.csv") -> Path:
        """Write ``content`` to a CSV inside ``dir_path``."""
        csv_path = dir_path / name
        csv_path.write_text(content, encoding="utf-8")
        return csv_path

    def test_missing_input_raises(self) -> None:
        """Processing a missing input file raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                process_email_csv(
                    input_file=Path(tmpdir) / "ghost.csv",
                    output_file=Path(tmpdir) / "out.csv",
                    email_column="email",
                )

    def test_empty_csv_raises_valueerror(self) -> None:
        """A zero-byte CSV raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty = self._write_csv(Path(tmpdir), "")
            with self.assertRaises(ValueError):
                process_email_csv(
                    input_file=empty,
                    output_file=Path(tmpdir) / "out.csv",
                    email_column="email",
                )

    def test_unknown_column_raises_valueerror(self) -> None:
        """An unknown column name raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._write_csv(Path(tmpdir), "id,email\n1,a@example.com\n")
            with self.assertRaises(ValueError):
                process_email_csv(
                    input_file=src,
                    output_file=Path(tmpdir) / "out.csv",
                    email_column="missing_col",
                )

    def test_digit_column_index_selection(self) -> None:
        """Numeric column arguments select by 0-based index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._write_csv(Path(tmpdir), "id,address\n1,b@example.com\n")
            stats = process_email_csv(
                input_file=src,
                output_file=Path(tmpdir) / "out.csv",
                email_column="1",
            )
        self.assertEqual(stats["VALID"], 1)

    def test_case_insensitive_column_match(self) -> None:
        """Column matching ignores case differences."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._write_csv(Path(tmpdir), "id,EMAIL\n1,c@example.com\n")
            stats = process_email_csv(
                input_file=src,
                output_file=Path(tmpdir) / "out.csv",
                email_column="email",
            )
        self.assertEqual(stats["VALID"], 1)

    def test_short_and_blank_rows_handled(self) -> None:
        """Blank rows are skipped; short rows get padded before extension."""
        content = "id,email\n" "\n" "1,d@example.com\n" "2\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._write_csv(Path(tmpdir), content)
            stats = process_email_csv(
                input_file=src,
                output_file=Path(tmpdir) / "out.csv",
                email_column="email",
            )
            out_text = (Path(tmpdir) / "out.csv").read_text(encoding="utf-8")
        self.assertEqual(stats["VALID"], 1)
        self.assertEqual(stats["EMPTY"], 1)
        # Padded short row must carry empty id plus appended columns.
        self.assertIn("2,,,EMPTY", out_text)

    def test_combined_output_when_no_flagged_file(self) -> None:
        """Without --output-flagged the main file holds all rows."""
        content = "id,email\n" "1,good@example.com\n" "2,bad-syntax\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._write_csv(Path(tmpdir), content)
            process_email_csv(
                input_file=src,
                output_file=Path(tmpdir) / "out.csv",
                email_column="email",
                dedupe=False,
            )
            out_text = (Path(tmpdir) / "out.csv").read_text(encoding="utf-8")
        self.assertIn("good@example.com,VALID", out_text)
        self.assertIn("bad-syntax,INVALID_SYNTAX", out_text)


class TestCliParsingAndMain(unittest.TestCase):
    """Tests for argument parsing and the CLI flow."""

    def test_parse_args_defaults(self) -> None:
        """Required args parse; optional flags default sensibly."""
        args = parse_args(["-i", "in.csv", "-o", "out.csv", "-c", "email"])
        self.assertEqual(args.input_file, Path("in.csv"))
        self.assertEqual(args.output_file, Path("out.csv"))
        self.assertFalse(args.check_mx)
        self.assertTrue(args.dedupe)
        self.assertIsNone(args.output_flagged)

    def test_parse_args_flag_overrides(self) -> None:
        """--check-mx and --no-dedupe flip their respective options."""
        args = parse_args(
            [
                "-i",
                "in.csv",
                "-o",
                "out.csv",
                "-c",
                "0",
                "--check-mx",
                "--no-dedupe",
                "--output-flagged",
                "flag.csv",
            ]
        )
        self.assertTrue(args.check_mx)
        self.assertFalse(args.dedupe)
        self.assertEqual(args.output_flagged, Path("flag.csv"))

    def _run_main(self, argv: list) -> tuple:
        """Run main() with patched argv; return (code, stdout, stderr)."""
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with mock.patch.object(sys, "argv", ["main.py"] + argv):
                try:
                    main_module.main()
                except SystemExit as exc:
                    code = int(exc.code if exc.code is not None else 0)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_main_success_prints_stats(self) -> None:
        """Successful runs print per-status counts and output location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "in.csv"
            src.write_text("id,email\n1,ok@example.com\n", encoding="utf-8")
            out_path = Path(tmpdir) / "out.csv"
            code, out, err = self._run_main(
                ["-i", str(src), "-o", str(out_path), "-c", "email"]
            )
        self.assertEqual(code, 0)
        self.assertIn("Email validation and cleaning complete.", out)
        self.assertIn("VALID: 1", out)
        self.assertIn(f"Output saved to: {out_path}", out)
        self.assertEqual(err, "")

    def test_main_error_exits_one(self) -> None:
        """Failures print to stderr and exit with code 1."""
        code, out, err = self._run_main(
            ["-i", "Z:/missing.csv", "-o", "out.csv", "-c", "email"]
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("Error:", err)

    def test_main_flagged_message_displayed(self) -> None:
        """When --output-flagged is used its path is echoed back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "in.csv"
            src.write_text("id,email\n1,ok@example.com\n2,nope\n", encoding="utf-8")
            out_path = Path(tmpdir) / "out.csv"
            flag_path = Path(tmpdir) / "flagged.csv"
            code, out, _ = self._run_main(
                [
                    "-i",
                    str(src),
                    "-o",
                    str(out_path),
                    "-c",
                    "email",
                    "--output-flagged",
                    str(flag_path),
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn(f"Flagged records saved to: {flag_path}", out)


if __name__ == "__main__":
    unittest.main()

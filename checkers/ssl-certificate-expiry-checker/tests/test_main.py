"""Unit tests for SSL Certificate Expiry Checker."""

import contextlib
import datetime
import io
import json
import unittest
from unittest.mock import MagicMock, patch

from main import (
    check_domain_expiry,
    format_report_table,
    get_cert_expiry_date,
    main,
    parse_args,
)


class TestSSLCertificateExpiryChecker(unittest.TestCase):

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_get_cert_expiry_date_success(
        self, mock_create_conn: MagicMock, mock_ssl_context: MagicMock
    ) -> None:
        mock_sock = MagicMock()
        mock_ssock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock
        mock_wrap = mock_ssl_context.return_value.wrap_socket
        mock_wrap.return_value.__enter__.return_value = mock_ssock

        mock_ssock.getpeercert.return_value = {"notAfter": "Dec 31 23:59:59 2030 GMT"}

        expiry = get_cert_expiry_date("example.com", 443)
        self.assertEqual(expiry.year, 2030)
        self.assertEqual(expiry.month, 12)
        self.assertEqual(expiry.day, 31)

    @patch("main.get_cert_expiry_date")
    def test_check_domain_expiry_ok(self, mock_get_expiry: MagicMock) -> None:
        delta = datetime.timedelta(days=60)
        future_date = datetime.datetime.now(datetime.timezone.utc) + delta
        mock_get_expiry.return_value = future_date

        res = check_domain_expiry("example.com", warning_days=30)
        self.assertEqual(res["status"], "OK")
        self.assertFalse(res["warning"])
        self.assertGreaterEqual(res["days_remaining"], 59)

    @patch("main.get_cert_expiry_date")
    def test_check_domain_expiry_warning(self, mock_get_expiry: MagicMock) -> None:
        delta = datetime.timedelta(days=10)
        soon_date = datetime.datetime.now(datetime.timezone.utc) + delta
        mock_get_expiry.return_value = soon_date

        res = check_domain_expiry("example.com", warning_days=30)
        self.assertEqual(res["status"], "WARNING")
        self.assertTrue(res["warning"])

    @patch("main.get_cert_expiry_date")
    def test_check_domain_expiry_error(self, mock_get_expiry: MagicMock) -> None:
        mock_get_expiry.side_effect = Exception("Connection refused")

        res = check_domain_expiry("invalid.domain")
        self.assertEqual(res["status"], "ERROR")
        self.assertTrue(res["warning"])
        self.assertEqual(res["error"], "Connection refused")

    def test_format_report_table(self) -> None:
        results = [
            {
                "domain": "example.com",
                "port": 443,
                "expiry_date": "2030-12-31 23:59:59 UTC",
                "days_remaining": 100,
                "status": "OK",
                "warning": False,
                "error": None,
            }
        ]
        table = format_report_table(results)
        self.assertIn("example.com", table)
        self.assertIn("OK", table)


class TestSSLCheckerEdgeCases(unittest.TestCase):
    """Edge-case and CLI coverage for the certificate expiry checker."""

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_get_cert_expiry_date_without_not_after(
        self, mock_create_conn: MagicMock, mock_ssl_context: MagicMock
    ) -> None:
        """A peer certificate lacking notAfter must raise a clear ValueError."""
        mock_sock = MagicMock()
        mock_ssock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock
        wrap_mock = mock_ssl_context.return_value.wrap_socket
        wrap_mock.return_value.__enter__.return_value = mock_ssock
        mock_ssock.getpeercert.return_value = {}

        with self.assertRaises(ValueError) as ctx:
            get_cert_expiry_date("bad.example.com", 443)
        self.assertIn("No valid SSL certificate", str(ctx.exception))

    @patch("main.get_cert_expiry_date")
    def test_check_domain_expiry_expired(self, mock_get_expiry: MagicMock) -> None:
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)
        mock_get_expiry.return_value = past

        res = check_domain_expiry("old.example.com", warning_days=30)
        self.assertEqual(res["status"], "EXPIRED")
        self.assertTrue(res["warning"])
        self.assertLess(res["days_remaining"], 0)

    def test_format_report_table_renders_error_rows(self) -> None:
        results = [
            {
                "domain": "down.example.com",
                "port": 443,
                "expiry_date": None,
                "days_remaining": None,
                "status": "ERROR",
                "warning": True,
                "error": "connection refused",
            }
        ]
        table = format_report_table(results)
        self.assertIn("N/A", table)
        self.assertIn("ERROR", table)

    @patch("main.get_cert_expiry_date")
    def test_main_splits_domain_and_custom_port(
        self, mock_get_expiry: MagicMock
    ) -> None:
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            days=200
        )
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        mock_get_expiry.side_effect = [future, past]

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["ok.example.com", "expired.example.com:8443"])
        self.assertEqual(ret, 1)
        ports = [call.args[1] for call in mock_get_expiry.call_args_list]
        self.assertEqual(ports, [443, 8443])
        self.assertIn("EXPIRED", buf.getvalue())

    @patch("main.get_cert_expiry_date")
    def test_main_json_output_all_ok(self, mock_get_expiry: MagicMock) -> None:
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            days=365
        )
        mock_get_expiry.return_value = future

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["--json", "fine.example.com"])
        self.assertEqual(ret, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload[0]["status"], "OK")
        self.assertIsNone(payload[0]["error"])

    def test_parse_args_defaults_and_flags(self) -> None:
        parsed = parse_args(["a.com"])
        self.assertEqual(parsed.domains, ["a.com"])
        self.assertEqual(parsed.warning_days, 30)
        self.assertEqual(parsed.timeout, 10.0)
        self.assertFalse(parsed.json)

        parsed = parse_args(["a.com", "b.com:9443", "-w", "7", "--json"])
        self.assertEqual(len(parsed.domains), 2)
        self.assertEqual(parsed.warning_days, 7)
        self.assertTrue(parsed.json)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for SSL Certificate Expiry Checker."""

import datetime
import unittest
from unittest.mock import MagicMock, patch

from main import check_domain_expiry, format_report_table, get_cert_expiry_date


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


if __name__ == "__main__":
    unittest.main()

"""Unit tests for SSL/Domain Expiry Monitor."""

import datetime
import os
import socket
import sys
import unittest
from unittest.mock import MagicMock, patch

import requests

# Workaround for hyphenated folder module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error,wrong-import-position
import expiry_monitor  # noqa: E402


class TestExpiryMonitor(unittest.TestCase):
    """Test suite for expiry_monitor functions."""

    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    def test_get_ssl_expiry_healthy(
        self, mock_create_context: MagicMock, mock_create_conn: MagicMock
    ) -> None:
        """Test get_ssl_expiry returns correct metrics for valid cert."""
        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock

        mock_wrap_sock = MagicMock()
        mock_context_instance = mock_create_context.return_value
        mock_context_instance.wrap_socket.return_value.__enter__.return_value = (
            mock_wrap_sock
        )

        future_date = datetime.datetime.utcnow() + datetime.timedelta(days=40)
        date_str = future_date.strftime("%b %d %H:%M:%S %Y")
        mock_wrap_sock.getpeercert.return_value = {"notAfter": f"{date_str} GMT"}

        res = expiry_monitor.get_ssl_expiry("example.com")
        self.assertIsNone(res["error"])
        self.assertEqual(res["expiry_date"], future_date.date().isoformat())
        self.assertIn(res["days_left"], (39, 40))

    @patch("whois.whois")
    def test_get_domain_expiry_single_date(self, mock_whois: MagicMock) -> None:
        """Test get_domain_expiry with a single datetime expiration."""
        future_date = datetime.datetime.utcnow() + datetime.timedelta(days=100)
        mock_w = MagicMock()
        mock_w.expiration_date = future_date
        mock_w.registrar = "GoDaddy"
        mock_whois.return_value = mock_w

        res = expiry_monitor.get_domain_expiry("example.com")
        self.assertIsNone(res["error"])
        self.assertEqual(res["expiry_date"], future_date.date().isoformat())
        self.assertIn(res["days_left"], (99, 100))
        self.assertEqual(res["registrar"], "GoDaddy")

    @patch("whois.whois")
    def test_get_domain_expiry_list_date(self, mock_whois: MagicMock) -> None:
        """Test get_domain_expiry when registrar returns expiration list."""
        future_date_1 = datetime.datetime.utcnow() + datetime.timedelta(days=100)
        future_date_2 = datetime.datetime.utcnow() + datetime.timedelta(days=105)
        mock_w = MagicMock()
        mock_w.expiration_date = [future_date_1, future_date_2]
        mock_w.registrar = "Namecheap"
        mock_whois.return_value = mock_w

        res = expiry_monitor.get_domain_expiry("example.com")
        self.assertIsNone(res["error"])
        self.assertEqual(res["expiry_date"], future_date_1.date().isoformat())
        self.assertIn(res["days_left"], (99, 100))

    def test_evaluate_status(self) -> None:
        """Test threshold evaluation labelling."""
        # Warn threshold 30, crit threshold 15
        self.assertEqual(expiry_monitor.evaluate_status(45, 30, 15), "HEALTHY")
        self.assertEqual(expiry_monitor.evaluate_status(25, 30, 15), "WARNING")
        self.assertEqual(expiry_monitor.evaluate_status(10, 30, 15), "CRITICAL")
        self.assertEqual(expiry_monitor.evaluate_status(-5, 30, 15), "EXPIRED")
        self.assertEqual(expiry_monitor.evaluate_status(None, 30, 15), "UNKNOWN")

    @patch("expiry_monitor.get_ssl_expiry")
    @patch("expiry_monitor.get_domain_expiry")
    def test_check_domain_expiry(
        self, mock_get_domain: MagicMock, mock_get_ssl: MagicMock
    ) -> None:
        """Test check_domain_expiry consolidated mapping."""
        mock_get_ssl.return_value = {
            "expiry_date": "2026-08-17",
            "days_left": 40,
            "error": None,
        }
        mock_get_domain.return_value = {
            "expiry_date": "2026-10-16",
            "days_left": 100,
            "registrar": "GoDaddy",
            "error": None,
        }

        rep = expiry_monitor.check_domain_expiry(
            "example.com", warn_days=30, crit_days=15
        )
        self.assertEqual(rep["domain"], "example.com")
        self.assertEqual(rep["ssl"]["status"], "HEALTHY")
        self.assertEqual(rep["domain_reg"]["status"], "HEALTHY")
        self.assertEqual(rep["domain_reg"]["registrar"], "GoDaddy")

    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    def test_get_ssl_expiry_failures(
        self, mock_create_context: MagicMock, mock_create_conn: MagicMock
    ) -> None:
        """Test get_ssl_expiry error handling and UTC formatting."""
        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock
        mock_wrap_sock = MagicMock()
        mock_context_instance = mock_create_context.return_value
        mock_context_instance.wrap_socket.return_value.__enter__.return_value = (
            mock_wrap_sock
        )

        # 1. No certificate found
        mock_wrap_sock.getpeercert.return_value = None
        res = expiry_monitor.get_ssl_expiry("example.com")
        self.assertEqual(res["error"], "No certificate")

        # 2. Expiry date missing in cert
        mock_wrap_sock.getpeercert.return_value = {"issuer": "CA"}
        res = expiry_monitor.get_ssl_expiry("example.com")
        self.assertEqual(res["error"], "Expiry date missing")

        # 3. Expiry date with UTC suffix
        future_date = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=20)
        date_str = future_date.strftime("%b %d %H:%M:%S %Y")
        mock_wrap_sock.getpeercert.return_value = {"notAfter": f"{date_str} UTC"}
        res = expiry_monitor.get_ssl_expiry("example.com")
        self.assertIsNone(res["error"])
        self.assertEqual(res["expiry_date"], future_date.date().isoformat())

        # 4. Socket or general exception
        mock_create_conn.side_effect = socket.error("Connection failed")
        res = expiry_monitor.get_ssl_expiry("example.com")
        self.assertEqual(res["error"], "Connection failed")

    @patch("whois.whois")
    def test_get_domain_expiry_failures(self, mock_whois: MagicMock) -> None:
        """Test get_domain_expiry error scenarios."""
        # 1. Expiration date missing
        mock_w = MagicMock()
        mock_w.expiration_date = None
        mock_w.registrar = "GoDaddy"
        mock_whois.return_value = mock_w
        res = expiry_monitor.get_domain_expiry("example.com")
        self.assertEqual(res["error"], "No expiration date")

        # 2. Invalid expiration date type (e.g. string)
        mock_w.expiration_date = "2026-12-31"
        res = expiry_monitor.get_domain_expiry("example.com")
        self.assertIn("Invalid date type", res["error"])

        # 3. Whois raises exception
        mock_whois.side_effect = Exception("WHOIS lookup failed")
        res = expiry_monitor.get_domain_expiry("example.com")
        self.assertEqual(res["error"], "WHOIS lookup failed")

    @patch("expiry_monitor.get_ssl_expiry")
    @patch("expiry_monitor.get_domain_expiry")
    def test_check_domain_expiry_errors(
        self, mock_get_domain: MagicMock, mock_get_ssl: MagicMock
    ) -> None:
        """Test check_domain_expiry with error return states."""
        mock_get_ssl.return_value = {
            "expiry_date": None,
            "days_left": None,
            "error": "SSL handshake failure",
        }
        mock_get_domain.return_value = {
            "expiry_date": None,
            "days_left": None,
            "registrar": None,
            "error": "WHOIS timeout",
        }
        rep = expiry_monitor.check_domain_expiry("example.com")
        self.assertEqual(rep["ssl"]["status"], "ERROR")
        self.assertEqual(rep["domain_reg"]["status"], "ERROR")

    @patch("requests.post")
    def test_send_webhook(self, mock_post: MagicMock) -> None:
        """Test send_webhook successful POST and exceptions."""
        # No alerts: skipped
        expiry_monitor.send_webhook("https://webhook.site", [])
        mock_post.assert_not_called()

        # Success case
        mock_post.return_value = MagicMock(status_code=200)
        expiry_monitor.send_webhook("https://webhook.site", ["Alert message"])
        mock_post.assert_called_once()

        # Exception handled
        mock_post.side_effect = requests.RequestException("Webhook timeout")
        # Should not raise exception
        expiry_monitor.send_webhook("https://webhook.site", ["Alert message"])

    def test_print_report(self) -> None:
        """Test print_report console table printing."""
        import io
        from unittest.mock import patch

        reports = [
            {
                "domain": "healthy.com",
                "ssl": {
                    "expiry_date": "2026-10-10",
                    "status": "HEALTHY",
                    "error": None,
                },
                "domain_reg": {
                    "expiry_date": "2027-11-11",
                    "status": "HEALTHY",
                    "error": None,
                },
            },
            {
                "domain": "error.com",
                "ssl": {
                    "expiry_date": None,
                    "status": "ERROR",
                    "error": "Connection error",
                },
                "domain_reg": {
                    "expiry_date": None,
                    "status": "ERROR",
                    "error": "WHOIS error",
                },
            },
        ]

        f = io.StringIO()
        with patch("sys.stdout", new=f):
            expiry_monitor.print_report(reports)

        output = f.getvalue()
        self.assertIn("healthy.com", output)
        self.assertIn("Connection error", output)
        self.assertIn("WHOIS error", output)

    @patch("expiry_monitor.check_domain_expiry")
    @patch("expiry_monitor.send_webhook")
    def test_main_cli(self, mock_webhook: MagicMock, mock_check: MagicMock) -> None:
        """Test main CLI entry point parser and behaviors."""
        # 1. Mutually exclusive option failure exits 2
        with self.assertRaises(SystemExit) as exc:
            expiry_monitor.main([])
        self.assertEqual(exc.exception.code, 2)

        # 2. Domain list file not found exits 2
        with self.assertRaises(SystemExit) as exc:
            expiry_monitor.main(["-f", "missing_domain_file.txt"])
        self.assertEqual(exc.exception.code, 2)

        # 3. Domain list file loading success
        import tempfile

        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write("domain1.com\n# Comment line\n\ndomain2.com\n")
            temp_path = tmp.name

        mock_check.return_value = {
            "domain": "domain1.com",
            "ssl": {
                "expiry_date": "2026-10-10",
                "days_left": 40,
                "status": "HEALTHY",
                "error": None,
            },
            "domain_reg": {
                "expiry_date": "2026-12-12",
                "days_left": 90,
                "status": "HEALTHY",
                "error": None,
            },
        }

        import io
        from unittest.mock import patch

        f = io.StringIO()
        try:
            with patch("sys.stdout", new=f):
                with self.assertRaises(SystemExit) as exc:
                    expiry_monitor.main(["-f", temp_path, "-j"])
                self.assertEqual(exc.exception.code, 0)
            self.assertIn('"domain": "domain1.com"', f.getvalue())
        finally:
            os.remove(temp_path)

        # 4. Failure outcomes (EXPIRED / ERROR SSL or WHOIS states) exits 1
        mock_check.return_value = {
            "domain": "failed.com",
            "ssl": {
                "expiry_date": None,
                "days_left": None,
                "status": "ERROR",
                "error": "Handshake failed",
            },
            "domain_reg": {
                "expiry_date": "2026-07-10",
                "days_left": 1,
                "status": "CRITICAL",
                "error": None,
            },
        }
        with self.assertRaises(SystemExit) as exc:
            expiry_monitor.main(["-d", "failed.com", "--webhook", "https://web.com"])
        self.assertEqual(exc.exception.code, 1)
        mock_webhook.assert_called_once()


if __name__ == "__main__":
    unittest.main()

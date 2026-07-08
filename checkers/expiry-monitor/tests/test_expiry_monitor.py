"""Unit tests for SSL/Domain Expiry Monitor."""

import datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Workaround for hyphenated folder module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error,wrong-import-position
import expiry_monitor


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
        mock_create_context.return_value.wrap_socket.return_value.__enter__.return_value = mock_wrap_sock

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
        mock_get_ssl.return_value = {"expiry_date": "2026-08-17", "days_left": 40, "error": None}
        mock_get_domain.return_value = {
            "expiry_date": "2026-10-16",
            "days_left": 100,
            "registrar": "GoDaddy",
            "error": None,
        }

        rep = expiry_monitor.check_domain_expiry("example.com", warn_days=30, crit_days=15)
        self.assertEqual(rep["domain"], "example.com")
        self.assertEqual(rep["ssl"]["status"], "HEALTHY")
        self.assertEqual(rep["domain_reg"]["status"], "HEALTHY")
        self.assertEqual(rep["domain_reg"]["registrar"], "GoDaddy")


if __name__ == "__main__":
    unittest.main()

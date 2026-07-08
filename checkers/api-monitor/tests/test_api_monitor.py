"""Unit tests for API Health Monitor."""

import datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Workaround for hyphenated folder module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error,wrong-import-position
import api_monitor


class TestApiMonitor(unittest.TestCase):
    """Test suite for api_monitor functions."""

    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    def test_check_ssl_expiry_healthy(
        self, mock_create_context: MagicMock, mock_create_conn: MagicMock
    ) -> None:
        """Test check_ssl_expiry with a healthy future certificate."""
        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock

        # Mock wrap_socket and peer certificate dictionary
        mock_wrap_sock = MagicMock()
        mock_create_context.return_value.wrap_socket.return_value.__enter__.return_value = mock_wrap_sock

        future_date = datetime.datetime.utcnow() + datetime.timedelta(days=45)
        # Format like 'Nov 25 12:00:00 2026'
        date_str = future_date.strftime("%b %d %H:%M:%S %Y")
        mock_wrap_sock.getpeercert.return_value = {"notAfter": f"{date_str} GMT"}

        res = api_monitor.check_ssl_expiry("https://example.com", warn_days=30)
        self.assertEqual(res["status"], "healthy")
        self.assertGreater(res["days_left"], 30)
        self.assertIsNone(res["error"])

    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    def test_check_ssl_expiry_warning(
        self, mock_create_context: MagicMock, mock_create_conn: MagicMock
    ) -> None:
        """Test check_ssl_expiry warning threshold trigger."""
        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock

        mock_wrap_sock = MagicMock()
        mock_create_context.return_value.wrap_socket.return_value.__enter__.return_value = mock_wrap_sock

        warning_date = datetime.datetime.utcnow() + datetime.timedelta(days=10)
        date_str = warning_date.strftime("%b %d %H:%M:%S %Y")
        mock_wrap_sock.getpeercert.return_value = {"notAfter": f"{date_str} GMT"}

        res = api_monitor.check_ssl_expiry("https://example.com", warn_days=30)
        self.assertEqual(res["status"], "warning")
        self.assertEqual(res["days_left"], 9)  # 10 days out matches ~9 remaining
        self.assertIsNone(res["error"])

    @patch("requests.get")
    @patch("api_monitor.check_ssl_expiry")
    def test_test_endpoint_healthy(
        self, mock_check_ssl: MagicMock, mock_get: MagicMock
    ) -> None:
        """Test testing endpoint under fully healthy conditions."""
        mock_check_ssl.return_value = {"status": "healthy", "days_left": 45, "error": None}
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"userId": 1, "id": 10, "title": "Test Title", "body": "Body Text"}
        mock_get.return_value = mock_response

        endpoint = {
            "name": "Test GET",
            "url": "https://example.com/api",
            "method": "GET",
            "expected_status": 200,
            "latency_threshold_ms": 1000,
            "schema": {
                "type": "object",
                "required": ["userId", "id"],
            },
        }

        report = api_monitor.test_endpoint(endpoint)
        self.assertTrue(report["status_ok"])
        self.assertTrue(report["latency_ok"])
        self.assertTrue(report["schema_ok"])
        self.assertEqual(report["ssl_status"], "healthy")
        self.assertEqual(len(report["errors"]), 0)

    @patch("requests.get")
    @patch("api_monitor.check_ssl_expiry")
    def test_test_endpoint_schema_mismatch(
        self, mock_check_ssl: MagicMock, mock_get: MagicMock
    ) -> None:
        """Test schema mismatch detection."""
        mock_check_ssl.return_value = {"status": "healthy", "days_left": 45, "error": None}

        mock_response = MagicMock()
        mock_response.status_code = 200
        # Missing required field 'userId'
        mock_response.json.return_value = {"id": 10, "title": "Test Title"}
        mock_get.return_value = mock_response

        endpoint = {
            "name": "Test GET",
            "url": "https://example.com/api",
            "method": "GET",
            "expected_status": 200,
            "schema": {
                "type": "object",
                "required": ["userId"],
            },
        }

        report = api_monitor.test_endpoint(endpoint)
        self.assertTrue(report["status_ok"])
        self.assertFalse(report["schema_ok"])
        self.assertIn("JSON Schema Validation Error", report["errors"][0])


if __name__ == "__main__":
    unittest.main()

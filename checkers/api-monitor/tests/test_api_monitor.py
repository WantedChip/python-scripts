"""Unit tests for API Health Monitor."""

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
import api_monitor  # noqa: E402


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
        mock_context_instance = mock_create_context.return_value
        mock_context_instance.wrap_socket.return_value.__enter__.return_value = (
            mock_wrap_sock
        )

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
        mock_context_instance = mock_create_context.return_value
        mock_context_instance.wrap_socket.return_value.__enter__.return_value = (
            mock_wrap_sock
        )

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
        mock_check_ssl.return_value = {
            "status": "healthy",
            "days_left": 45,
            "error": None,
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "userId": 1,
            "id": 10,
            "title": "Test Title",
            "body": "Body Text",
        }
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
        mock_check_ssl.return_value = {
            "status": "healthy",
            "days_left": 45,
            "error": None,
        }

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

    def test_check_ssl_expiry_non_https(self) -> None:
        """Test check_ssl_expiry with non-HTTPS schemes."""
        res = api_monitor.check_ssl_expiry("http://example.com")
        self.assertEqual(res["status"], "skipped")
        self.assertIsNone(res["days_left"])

    def test_check_ssl_expiry_invalid_hostname(self) -> None:
        """Test check_ssl_expiry with invalid hostnames."""
        res = api_monitor.check_ssl_expiry("https:///path")
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error"], "Invalid hostname")

    @patch("socket.create_connection")
    def test_check_ssl_expiry_socket_error(self, mock_create_conn: MagicMock) -> None:
        """Test check_ssl_expiry handles socket connection exceptions."""
        mock_create_conn.side_effect = socket.error("Connection timed out")
        res = api_monitor.check_ssl_expiry("https://example.com")
        self.assertEqual(res["status"], "error")
        self.assertIn("Connection timed out", res["error"])

    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    def test_check_ssl_expiry_no_cert_or_expiry(
        self, mock_create_context: MagicMock, mock_create_conn: MagicMock
    ) -> None:
        """Test check_ssl_expiry when no certificate or expiry is found."""
        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock
        mock_wrap_sock = MagicMock()
        mock_context_instance = mock_create_context.return_value
        mock_context_instance.wrap_socket.return_value.__enter__.return_value = (
            mock_wrap_sock
        )

        # Case 1: no cert
        mock_wrap_sock.getpeercert.return_value = None
        res1 = api_monitor.check_ssl_expiry("https://example.com")
        self.assertEqual(res1["status"], "error")
        self.assertEqual(res1["error"], "No certificate found")

        # Case 2: missing notAfter expiry date in cert
        mock_wrap_sock.getpeercert.return_value = {"issuer": "CA"}
        res2 = api_monitor.check_ssl_expiry("https://example.com")
        self.assertEqual(res2["status"], "error")
        self.assertEqual(res2["error"], "No expiry date in cert")

    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    def test_check_ssl_expiry_expired_and_utc(
        self, mock_create_context: MagicMock, mock_create_conn: MagicMock
    ) -> None:
        """Test check_ssl_expiry with expired and UTC suffixed certificate."""
        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock
        mock_wrap_sock = MagicMock()
        mock_context_instance = mock_create_context.return_value
        mock_context_instance.wrap_socket.return_value.__enter__.return_value = (
            mock_wrap_sock
        )

        # Case 1: expired date
        expired_date = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5)
        # Format like 'Nov 25 12:00:00 2026 UTC'
        date_str = expired_date.strftime("%b %d %H:%M:%S %Y")
        mock_wrap_sock.getpeercert.return_value = {"notAfter": f"{date_str} UTC"}

        # UTC is stripped, check_ssl_expiry uses utcnow()
        res = api_monitor.check_ssl_expiry("https://example.com")
        self.assertEqual(res["status"], "expired")
        self.assertLess(res["days_left"], 0)

    def test_test_endpoint_missing_url(self) -> None:
        """Test test_endpoint behavior when target URL is missing."""
        report = api_monitor.test_endpoint({"name": "No URL Target"})
        self.assertFalse(report["status_ok"])
        self.assertIn("Missing target URL", report["errors"])

    @patch("requests.post")
    @patch("api_monitor.check_ssl_expiry")
    def test_test_endpoint_post_method(
        self, mock_check_ssl: MagicMock, mock_post: MagicMock
    ) -> None:
        """Test test_endpoint sends a POST request with payload."""
        mock_check_ssl.return_value = {
            "status": "skipped",
            "days_left": None,
            "error": None,
        }
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_post.return_value = mock_response

        endpoint = {
            "name": "Test POST",
            "url": "http://example.com/api",
            "method": "POST",
            "payload": {"key": "value"},
            "expected_status": 201,
        }

        report = api_monitor.test_endpoint(endpoint)
        self.assertTrue(report["status_ok"])
        self.assertEqual(report["status_code"], 201)
        mock_post.assert_called_once_with(
            "http://example.com/api", json={"key": "value"}, headers=None, timeout=10
        )

    @patch("requests.get")
    @patch("api_monitor.check_ssl_expiry")
    def test_test_endpoint_mismatch_and_exceptions(
        self, mock_check_ssl: MagicMock, mock_get: MagicMock
    ) -> None:
        """Test test_endpoint with latency, status mismatches and exceptions."""
        mock_check_ssl.return_value = {
            "status": "healthy",
            "days_left": 45,
            "error": None,
        }

        # Case 1: Latency threshold and status mismatch
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        # Mock time delay to trigger latency check failure
        with patch("time.perf_counter", side_effect=[0.0, 2.0]):
            endpoint = {
                "url": "https://example.com/api",
                "expected_status": 200,
                "latency_threshold_ms": 100,
            }
            report = api_monitor.test_endpoint(endpoint)
            self.assertFalse(report["status_ok"])
            self.assertFalse(report["latency_ok"])
            self.assertIn("Status code mismatch", report["errors"][1])

        # Case 2: JSON decode failure in schema check
        mock_response_json_err = MagicMock()
        mock_response_json_err.status_code = 200
        mock_response_json_err.json.side_effect = requests.exceptions.JSONDecodeError(
            "not json", "", 0
        )
        mock_get.return_value = mock_response_json_err

        endpoint_schema = {
            "url": "https://example.com/api",
            "schema": {"type": "object"},
        }
        report_schema = api_monitor.test_endpoint(endpoint_schema)
        self.assertFalse(report_schema["schema_ok"])
        self.assertIn("Failed to decode JSON", report_schema["errors"][0])

        # Case 3: requests exception raised during HTTP request
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
        report_exc = api_monitor.test_endpoint({"url": "https://example.com/api"})
        self.assertFalse(report_exc["status_ok"])
        self.assertIn("HTTP Request failed", report_exc["errors"][0])

    def test_run_monitor_yaml_json(self) -> None:
        """Test run_monitor with JSON/YAML config formats."""
        import tempfile

        # JSON config
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as json_tmp:
            json_tmp.write('{"endpoints": [{"name": "JSON endpoint", "url": ""}]}')
            json_path = json_tmp.name

        # YAML config
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as yaml_tmp:
            yaml_tmp.write("endpoints:\n  - name: YAML endpoint\n    url: ''\n")
            yaml_path = yaml_tmp.name

        try:
            reports_json = api_monitor.run_monitor(json_path)
            self.assertEqual(len(reports_json), 1)
            self.assertEqual(reports_json[0]["name"], "JSON endpoint")

            reports_yaml = api_monitor.run_monitor(yaml_path)
            self.assertEqual(len(reports_yaml), 1)
            self.assertEqual(reports_yaml[0]["name"], "YAML endpoint")
        finally:
            os.remove(json_path)
            os.remove(yaml_path)

    def test_print_table(self) -> None:
        """Test print_table outputs correct formatted columns."""
        import io
        from unittest.mock import patch

        reports = [
            {
                "name": "Healthy Get",
                "url": "https://healthy.com",
                "method": "GET",
                "status_code": 200,
                "latency_ms": 50,
                "latency_ok": True,
                "status_ok": True,
                "schema_ok": True,
                "ssl_status": "healthy",
                "ssl_days": 40,
                "ssl_error": None,
                "errors": [],
            },
            {
                "name": "Failed Get",
                "url": "https://failed.com",
                "method": "GET",
                "status_code": 500,
                "latency_ms": 2000,
                "latency_ok": False,
                "status_ok": False,
                "schema_ok": True,
                "ssl_status": "expired",
                "ssl_days": -1,
                "ssl_error": None,
                "errors": [
                    "Latency exceeded threshold",
                    "Status code mismatch",
                    "SSL Certificate is EXPIRED",
                ],
            },
        ]

        f = io.StringIO()
        with patch("sys.stdout", new=f):
            api_monitor.print_table(reports)

        output = f.getvalue()
        self.assertIn("HEALTHY", output)
        self.assertIn("FAILED", output)
        self.assertIn("Latency exceeded threshold", output)

    def test_main_cli(self) -> None:
        """Test main CLI entry point scenarios."""
        # 1. Config file not found exits 2
        with self.assertRaises(SystemExit) as exc:
            api_monitor.main(["-c", "nonexistent_cfg.json"])
        self.assertEqual(exc.exception.code, 2)

        # 2. Main execution with healthy results exits 0
        import io

        f = io.StringIO()
        with patch("api_monitor.run_monitor") as mock_run:
            mock_run.return_value = [
                {
                    "status_ok": True,
                    "latency_ok": True,
                    "schema_ok": True,
                    "ssl_status": "healthy",
                    "errors": [],
                }
            ]
            with patch("sys.stdout", new=f):
                with self.assertRaises(SystemExit) as exc:
                    api_monitor.main(["-c", "dummy.json", "--json-output"])
                self.assertEqual(exc.exception.code, 0)
        self.assertIn('"ssl_status": "healthy"', f.getvalue())

        # 3. Main execution with failure results exits 1
        with patch("api_monitor.run_monitor") as mock_run:
            mock_run.return_value = [
                {
                    "name": "Failed Target",
                    "url": "https://example.com",
                    "method": "GET",
                    "status_code": 500,
                    "latency_ms": 200,
                    "ssl_days": 10,
                    "status_ok": False,
                    "latency_ok": True,
                    "schema_ok": True,
                    "ssl_status": "healthy",
                    "errors": ["Some HTTP error"],
                }
            ]
            f = io.StringIO()
            with patch("sys.stdout", new=f):
                with self.assertRaises(SystemExit) as exc:
                    api_monitor.main(["-c", "dummy.json"])
                self.assertEqual(exc.exception.code, 1)


if __name__ == "__main__":
    unittest.main()

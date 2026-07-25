"""Unit tests for service-status-checker main module."""

import unittest
from unittest.mock import MagicMock, patch

from main import inspect_service, process_services


class TestServiceStatusChecker(unittest.TestCase):
    """Test suite for service status checker."""

    @patch("main.check_systemd_service")
    @patch("main.check_process_running")
    def test_inspect_service_running_process(
        self, mock_check_proc: MagicMock, mock_check_sysd: MagicMock
    ) -> None:
        """Test inspecting a running process."""
        mock_check_sysd.return_value = False
        mock_check_proc.return_value = (True, [1234, 5678])

        result = inspect_service("python", check_systemd=False)
        self.assertEqual(result["service"], "python")
        self.assertEqual(result["status"], "RUNNING")
        self.assertEqual(result["pids"], [1234, 5678])

    @patch("main.inspect_service")
    @patch("main.restart_systemd_service")
    def test_process_services_auto_restart(
        self, mock_restart: MagicMock, mock_inspect: MagicMock
    ) -> None:
        """Test auto-restarting stopped services in process_services."""
        mock_inspect.side_effect = [
            {"service": "nginx", "status": "RUNNING", "pids": [100]},
            {"service": "redis", "status": "STOPPED", "pids": []},
        ]
        mock_restart.return_value = True

        report = process_services(["nginx", "redis"], auto_restart=True)
        self.assertEqual(report["total_services"], 2)
        self.assertEqual(report["stopped_count"], 1)
        self.assertEqual(report["restarted_count"], 1)
        self.assertEqual(report["overall_status"], "HEALTHY")


if __name__ == "__main__":
    unittest.main()

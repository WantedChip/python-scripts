"""Unit tests for service-status-checker main module."""

import json
import subprocess  # nosec B404
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, PropertyMock, patch

import psutil
from main import (
    check_process_running,
    check_systemd_service,
    inspect_service,
    main,
    parse_args,
    print_health_report,
    process_services,
    restart_systemd_service,
)


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


class TestSystemdBoundaries(unittest.TestCase):
    """Tests for systemctl interactions with subprocess mocked out."""

    @patch("main.shutil.which", return_value=None)
    def test_check_systemd_service_without_systemctl(
        self, _mock_which: MagicMock
    ) -> None:
        self.assertFalse(check_systemd_service("nginx"))
        self.assertFalse(restart_systemd_service("nginx"))

    @patch("main.shutil.which", return_value="/usr/bin/systemctl")
    @patch("main.subprocess.run")
    def test_check_systemd_service_active_states(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(stdout="active\n")
        self.assertTrue(check_systemd_service("nginx"))

        mock_run.return_value = MagicMock(stdout="inactive\n")
        self.assertFalse(check_systemd_service("nginx"))

    @patch("main.shutil.which", return_value="/usr/bin/systemctl")
    @patch("main.subprocess.run")
    def test_check_systemd_service_subprocess_error(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="systemctl", timeout=5)
        self.assertFalse(check_systemd_service("nginx"))

    @patch("main.shutil.which", return_value="/usr/bin/systemctl")
    @patch("main.subprocess.run")
    def test_restart_systemd_service_outcomes(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(restart_systemd_service("nginx"))

        mock_run.return_value = MagicMock(returncode=3)
        self.assertFalse(restart_systemd_service("nginx"))

        mock_run.side_effect = OSError("no systemd bus")
        self.assertFalse(restart_systemd_service("nginx"))


class TestProcessScanning(unittest.TestCase):
    """Tests for psutil-backed process matching and error handling."""

    @staticmethod
    def _proc(pid: int, name: str, cmdline: List[str]) -> MagicMock:
        proc = MagicMock()
        proc.info = {"pid": pid, "name": name, "cmdline": cmdline}
        return proc

    @patch("main.HAS_PSUTIL", True)
    @patch("main.psutil.process_iter")
    def test_check_process_running_matches_name_and_cmdline(
        self, mock_iter: MagicMock
    ) -> None:
        mock_iter.return_value = [
            self._proc(101, "nginx.exe", ["nginx", "-g", "daemon off;"]),
            self._proc(202, "python", ["python", "-m", "pg_server"]),
            self._proc(303, "chrome.exe", ["chrome"]),
        ]
        is_running, pids = check_process_running("NGINX")
        self.assertTrue(is_running)
        self.assertEqual(pids, [101])

        is_running, pids = check_process_running("pg_server")
        self.assertTrue(is_running)
        self.assertEqual(pids, [202])

        is_running, pids = check_process_running("mysql")
        self.assertFalse(is_running)
        self.assertEqual(pids, [])

    @patch("main.HAS_PSUTIL", True)
    @patch("main.psutil.process_iter")
    def test_check_process_running_tolerates_psutil_errors(
        self, mock_iter: MagicMock
    ) -> None:
        vanished = MagicMock(spec=["info"])
        type(vanished).info = PropertyMock(side_effect=psutil.NoSuchProcess(pid=404))
        denied = MagicMock(spec=["info"])
        type(denied).info = PropertyMock(side_effect=psutil.AccessDenied(pid=405))
        healthy = self._proc(505, "sshd", ["sshd", "-D"])

        mock_iter.return_value = [vanished, denied, healthy]
        is_running, pids = check_process_running("sshd")
        self.assertTrue(is_running)
        self.assertEqual(pids, [505])

    @patch("main.HAS_PSUTIL", False)
    def test_check_process_running_without_psutil(self) -> None:
        is_running, pids = check_process_running("anything")
        self.assertFalse(is_running)
        self.assertEqual(pids, [])


class TestServiceHealthWorkflow(unittest.TestCase):
    """Tests for inspection aggregation, restarts, and reporting."""

    @patch("main.check_systemd_service", return_value=True)
    @patch("main.shutil.which", return_value="/usr/bin/systemctl")
    def test_inspect_service_systemd_active_path(
        self, _mock_which: MagicMock, mock_sysd: MagicMock
    ) -> None:
        result = inspect_service("nginx")
        self.assertEqual(result["status"], "RUNNING")
        self.assertTrue(result["systemd_checked"])
        self.assertEqual(result["pids"], [])
        mock_sysd.assert_called_once_with("nginx")

    @patch("main.restart_systemd_service", return_value=False)
    @patch("main.inspect_service")
    def test_process_services_unhealthy_when_restart_fails(
        self, mock_inspect: MagicMock, mock_restart: MagicMock
    ) -> None:
        mock_inspect.return_value = {
            "service": "redis",
            "status": "STOPPED",
            "pids": [],
        }
        report = process_services(["redis"], auto_restart=True)
        self.assertFalse(report["services"][0]["restarted"])
        self.assertTrue(report["services"][0]["restart_failed"])
        self.assertEqual(report["services"][0]["status"], "STOPPED")
        self.assertEqual(report["restarted_count"], 0)
        self.assertEqual(report["overall_status"], "UNHEALTHY")

    @patch("main.restart_systemd_service", side_effect=[True, False])
    @patch("main.inspect_service")
    def test_process_services_degraded_partial_recovery(
        self, mock_inspect: MagicMock, _mock_restart: MagicMock
    ) -> None:
        mock_inspect.side_effect = [
            {"service": "a", "status": "STOPPED", "pids": []},
            {"service": "b", "status": "STOPPED", "pids": []},
            {"service": "c", "status": "RUNNING", "pids": [9]},
        ]
        report = process_services(["a", "b", "c"], auto_restart=True)
        self.assertEqual(report["stopped_count"], 2)
        self.assertEqual(report["restarted_count"], 1)
        self.assertEqual(report["overall_status"], "DEGRADED")

    def test_print_health_report_renders_all_variants(self) -> None:
        report = {
            "overall_status": "DEGRADED",
            "total_services": 3,
            "running_count": 1,
            "stopped_count": 2,
            "restarted_count": 1,
            "services": [
                {
                    "service": "ok-svc",
                    "status": "RUNNING",
                    "systemd_checked": True,
                    "pids": [11, 22],
                },
                {
                    "service": "fixed-svc",
                    "status": "RESTARTED",
                    "systemd_checked": True,
                    "pids": [],
                    "restarted": True,
                },
                {
                    "service": "dead-svc",
                    "status": "STOPPED",
                    "systemd_checked": True,
                    "pids": [],
                    "restart_failed": True,
                },
            ],
        }
        buf = StringIO()
        with redirect_stdout(buf):
            print_health_report(report)
        output = buf.getvalue()
        self.assertIn("OVERALL: DEGRADED", output)
        self.assertIn("PIDs: [11, 22]", output)
        self.assertIn("(Restart Attempted)", output)
        self.assertIn("(Restart Failed)", output)

    def test_parse_args_defaults_and_flags(self) -> None:
        parsed = parse_args(["nginx"])
        self.assertEqual(parsed.services, ["nginx"])
        self.assertFalse(parsed.restart)
        self.assertIsNone(parsed.output_json)

        parsed = parse_args(["nginx", "--restart", "-o", "health.json"])
        self.assertTrue(parsed.restart)
        self.assertEqual(parsed.output_json, "health.json")

    def test_main_exports_json_report(self) -> None:
        fake_report: dict[str, Any] = {
            "overall_status": "HEALTHY",
            "total_services": 1,
            "running_count": 1,
            "stopped_count": 0,
            "restarted_count": 0,
            "services": [
                {
                    "service": "nginx",
                    "status": "RUNNING",
                    "systemd_checked": False,
                    "pids": [7],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "health.json"
            with patch("main.process_services", return_value=fake_report):
                buf = StringIO()
                with redirect_stdout(buf):
                    ret = main(["nginx", "--output-json", str(out_path)])
            self.assertEqual(ret, 0)
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(data["overall_status"], "HEALTHY")
            self.assertIn("exported to", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

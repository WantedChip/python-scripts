"""Tests for the System Uptime Reporter tool."""

import contextlib
import io
import json
import runpy
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import main as uptime_module
from main import (
    build_parser,
    format_text_report,
    format_uptime_duration,
    get_boot_timestamp,
    get_load_averages,
    get_system_uptime_report,
    main,
)


class TestSystemUptimeReporter(unittest.TestCase):

    def test_format_uptime_duration(self) -> None:
        self.assertEqual(format_uptime_duration(45), "45 secs")
        self.assertEqual(format_uptime_duration(125), "2 mins, 5 secs")
        self.assertEqual(format_uptime_duration(3665), "1 hour, 1 min, 5 secs")
        self.assertEqual(format_uptime_duration(90061), "1 day, 1 hour, 1 min, 1 sec")

    @patch("main.get_boot_timestamp")
    def test_get_system_uptime_report(self, mock_boot: MagicMock) -> None:
        fake_boot_time = time.time() - 3600  # 1 hour ago
        mock_boot.return_value = fake_boot_time

        report = get_system_uptime_report()
        self.assertIn("hostname", report)
        self.assertIn("boot_iso_utc", report)
        self.assertGreaterEqual(report["uptime_seconds"], 3599)
        self.assertIn("hour", report["uptime_formatted"])

    def test_format_text_report(self) -> None:
        report = {
            "hostname": "test-host",
            "platform": "Linux-5.4",
            "boot_iso_utc": "2026-01-01 00:00:00 UTC",
            "uptime_formatted": "2 days, 4 hours",
            "load_average": {"1m": 0.5, "5m": 0.3, "15m": 0.1},
        }
        text = format_text_report(report)
        self.assertIn("test-host", text)
        self.assertIn("2 days, 4 hours", text)
        self.assertIn("Load Average", text)


class TestBootTimestamp(unittest.TestCase):
    """Tests for boot timestamp resolution and fallbacks."""

    def test_psutil_boot_time_used_when_available(self) -> None:
        """psutil.boot_time() is preferred when psutil is importable."""
        with patch.object(uptime_module.psutil, "boot_time", return_value=1234.5):
            self.assertEqual(get_boot_timestamp(), 1234.5)

    def test_linux_proc_fallback(self) -> None:
        """On Linux the /proc/uptime file provides the fallback estimate."""
        proc_contents = "7200.5 14400.0\n"

        def fake_open(path: str, *args: Any, **kwargs: Any) -> MagicMock:
            if path == "/proc/uptime":
                handle = MagicMock()
                handle.__enter__.return_value.readline.return_value = proc_contents
                return handle
            raise FileNotFoundError(path)

        with patch.object(uptime_module, "HAS_PSUTIL", False):
            with patch.object(uptime_module.platform, "system", return_value="Linux"):
                with patch("builtins.open", side_effect=fake_open):
                    boot = get_boot_timestamp()
        expected = time.time() - 7200.5
        self.assertAlmostEqual(boot, expected, delta=2.0)

    def test_windows_gettickcount_fallback(self) -> None:
        """On Windows GetTickCount64 provides the fallback estimate."""
        fake_lib = MagicMock()
        fake_lib.GetTickCount64.return_value = 90_000  # 90 seconds of uptime

        fake_ctypes = MagicMock()
        fake_ctypes.windll.kernel32 = fake_lib

        with patch.object(uptime_module, "HAS_PSUTIL", False):
            with patch.object(uptime_module.platform, "system", return_value="Windows"):
                with patch.dict(sys.modules, {"ctypes": fake_ctypes}):
                    boot = get_boot_timestamp()
        self.assertAlmostEqual(boot, time.time() - 90.0, delta=2.0)

    def test_unknown_platform_defaults_to_now(self) -> None:
        """Unsupported platforms fall back to the current time."""
        with patch.object(uptime_module, "HAS_PSUTIL", False):
            with patch.object(uptime_module.platform, "system", return_value="SunOS"):
                boot = get_boot_timestamp()
        self.assertAlmostEqual(boot, time.time(), delta=2.0)


class TestLoadAverages(unittest.TestCase):
    """Tests for load average collection across platforms."""

    @staticmethod
    def failing_getloadavg() -> tuple:
        """Simulate a platform where load averages cannot be read."""
        raise OSError("unsupported")

    def test_os_getloadavg_values_are_rounded(self) -> None:
        """os.getloadavg results populate rounded 1/5/15 minute entries."""

        def fake_getloadavg() -> tuple:
            return (0.111, 0.222, 0.333)

        with patch.object(
            uptime_module.os, "getloadavg", create=True, new=fake_getloadavg
        ):
            loads = get_load_averages()
        self.assertEqual(loads["1m"], 0.11)
        self.assertEqual(loads["5m"], 0.22)
        self.assertEqual(loads["15m"], 0.33)

    def test_psutil_load_average_fallback(self) -> None:
        """Without os.getloadavg, psutil.getloadavg supplies the metrics."""
        fake_os = MagicMock(spec=["name"])  # has no getloadavg attribute
        with patch.object(uptime_module, "os", fake_os):
            with patch.object(
                uptime_module.psutil,
                "getloadavg",
                create=True,
                return_value=(1.25, 2.5, 3.75),
            ):
                loads = get_load_averages()
        self.assertEqual(loads["1m"], 1.25)
        self.assertEqual(loads["5m"], 2.5)
        self.assertEqual(loads["15m"], 3.75)

    def test_cpu_percent_used_when_no_load_source_works(self) -> None:
        """When every load source fails, CPU usage percentage is reported."""
        fake_os = MagicMock(spec=["name"])
        with patch.object(uptime_module, "os", fake_os):
            with patch.object(
                uptime_module.psutil,
                "getloadavg",
                create=True,
                side_effect=self.failing_getloadavg,
            ):
                with patch.object(
                    uptime_module.psutil,
                    "cpu_percent",
                    create=True,
                    return_value=42.7,
                ):
                    loads = get_load_averages()
        self.assertIsNone(loads["1m"])
        self.assertAlmostEqual(loads["cpu_usage_percent"], 42.7)

    def test_all_sources_unavailable_returns_nones(self) -> None:
        """With psutil absent entirely only None entries are returned."""
        fake_os = MagicMock(spec=["name"])
        with patch.object(uptime_module, "os", fake_os):
            with patch.object(uptime_module, "HAS_PSUTIL", False):
                loads = get_load_averages()
        self.assertIsNone(loads["1m"])
        self.assertIsNone(loads["5m"])
        self.assertIsNone(loads["15m"])
        self.assertNotIn("cpu_usage_percent", loads)


class TestReportRendering(unittest.TestCase):
    """Tests for combined report generation and text rendering."""

    def test_report_includes_all_sections(self) -> None:
        """The generated report contains platform and load information."""
        report = get_system_uptime_report()
        for key in [
            "hostname",
            "platform",
            "boot_timestamp",
            "boot_iso_utc",
            "uptime_seconds",
            "uptime_formatted",
            "load_average",
        ]:
            self.assertIn(key, report)
        self.assertIsInstance(report["load_average"], dict)

    def test_text_report_with_cpu_usage_line(self) -> None:
        """Systems reporting only CPU usage render a CPU Usage line."""
        report: Dict[str, Any] = {
            "hostname": "win-box",
            "platform": "Windows-10",
            "boot_iso_utc": "2026-08-01 08:00:00 UTC",
            "uptime_formatted": "3 hours, 30 mins",
            "load_average": {
                "1m": None,
                "5m": None,
                "15m": None,
                "cpu_usage_percent": 8,
            },
        }
        text = format_text_report(report)
        self.assertIn("CPU Usage       : 8%", text)
        self.assertNotIn("Load Average", text)

    def test_text_report_without_any_metrics(self) -> None:
        """No metric lines are emitted when both sources are missing."""
        report: Dict[str, Any] = {
            "hostname": "bare",
            "platform": "FreeBSD",
            "boot_iso_utc": "2026-08-01 08:00:00 UTC",
            "uptime_formatted": "10 mins",
            "load_average": {"1m": None, "5m": None, "15m": None},
        }
        text = format_text_report(report)
        self.assertNotIn("Load Average", text)
        self.assertNotIn("CPU Usage", text)
        self.assertIn("========== System Uptime Report ==========", text)


class TestCommandLine(unittest.TestCase):
    """Tests for CLI argument handling."""

    def run_main_capture(self, args: list) -> tuple:
        """Run main() capturing stdout and returning (code, output)."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(args)
        return code, buffer.getvalue()

    def test_default_output_is_text_report(self) -> None:
        """Without --json the human-readable report is printed."""
        code, output = self.run_main_capture([])
        self.assertEqual(code, 0)
        self.assertIn("System Uptime Report", output)
        self.assertIn("Hostname", output)

    def test_json_output_is_valid_json(self) -> None:
        """--json emits parseable JSON containing uptime data."""
        code, output = self.run_main_capture(["--json"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertIn("uptime_seconds", payload)
        self.assertIn("hostname", payload)

    def test_json_flag_is_declared(self) -> None:
        """The parser accepts --json as a boolean store_true flag."""
        self.assertFalse(build_parser().parse_args([]).json)
        self.assertTrue(build_parser().parse_args(["--json"]).json)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program exits cleanly with JSON output."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        argv = [entry, "--json"]
        with patch.object(sys, "argv", argv):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(entry, run_name="__main__")
        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertIn("uptime_seconds", payload)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for disk-usage-monitor main module."""

import io
import json
import logging
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from main import (
    check_disk_usage,
    evaluate_thresholds,
    export_report_json,
    get_mount_points,
    main,
    setup_logger,
)


class TestDiskUsageMonitor(unittest.TestCase):
    """Test suite for disk usage monitor."""

    @patch("shutil.disk_usage")
    def test_check_disk_usage(self, mock_disk_usage: MagicMock) -> None:
        """Test retrieving formatted disk metrics."""
        # 100 GB total, 80 GB used, 20 GB free
        gb = 1024**3
        mock_disk_usage.return_value = shutil._ntuple_diskusage(
            100 * gb, 80 * gb, 20 * gb
        )

        metrics = check_disk_usage("/fake/path")
        self.assertEqual(metrics["mount"], "/fake/path")
        self.assertEqual(metrics["total_gb"], 100.0)
        self.assertEqual(metrics["used_gb"], 80.0)
        self.assertEqual(metrics["free_gb"], 20.0)
        self.assertEqual(metrics["free_percent"], 20.0)
        self.assertEqual(metrics["used_percent"], 80.0)

    def test_evaluate_thresholds_trigger_alert(self) -> None:
        """Test alert generation when free space is below threshold."""
        usage_data = [
            {"mount": "/dev/sda1", "free_percent": 10.0, "free_gb": 5.0},
            {"mount": "/dev/sdb1", "free_percent": 30.0, "free_gb": 15.0},
        ]
        logger = logging.getLogger("TestLogger")
        logger.addHandler(logging.NullHandler())

        alerts = evaluate_thresholds(usage_data, threshold_percent=15.0, logger=logger)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["mount"], "/dev/sda1")
        self.assertEqual(alerts[0]["free_percent"], 10.0)

    def test_get_mount_points(self) -> None:
        """Test retrieving mount points list returns non-empty list."""
        mounts = get_mount_points()
        self.assertIsInstance(mounts, list)
        self.assertGreater(len(mounts), 0)


class TestDiskUsageMonitorHelpers(unittest.TestCase):
    """Logger setup, mount discovery and report export helpers."""

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        monitor_logger = logging.getLogger("DiskUsageMonitor")
        for handler in list(monitor_logger.handlers):
            handler.close()
            monitor_logger.removeHandler(handler)
        self.temp_dir.cleanup()

    def test_setup_logger_writes_to_file(self) -> None:
        """A log file receives formatted records when provided."""
        log_path = self.dir_path / "monitor.log"
        logger = setup_logger(str(log_path))
        logger.info("hello monitor")
        for handler in list(logger.handlers):
            handler.flush()
        content = log_path.read_text(encoding="utf-8")
        self.assertIn("hello monitor", content)

    def test_check_disk_usage_zero_total_is_safe(self) -> None:
        """Zero-capacity disks yield zero percentages without dividing."""
        with patch(
            "main.shutil.disk_usage",
            return_value=shutil._ntuple_diskusage(0, 0, 0),
        ):
            metrics = check_disk_usage("/empty")
        self.assertEqual(metrics["free_percent"], 0.0)
        self.assertEqual(metrics["used_percent"], 0.0)

    @patch("main.HAS_PSUTIL", True)
    @patch("main.psutil", create=True)
    def test_partition_failure_falls_back_to_drives(
        self, mock_psutil: MagicMock
    ) -> None:
        """psutil partition errors trigger the drive-letter fallback."""
        mock_psutil.disk_partitions.side_effect = RuntimeError("boom")
        with patch("main.os.name", "nt"), patch(
            "main.os.path.exists", return_value=True
        ):
            mounts = get_mount_points()
        self.assertIn("C:\\", mounts)

    @patch("main.HAS_PSUTIL", False)
    def test_no_psutil_falls_back_to_drive_letters(self) -> None:
        """Without psutil the Windows drive scan is used directly."""
        with patch("main.os.name", "nt"), patch(
            "main.os.path.exists",
            side_effect=lambda path: str(path).endswith(":\\"),
        ):
            mounts = get_mount_points()
        self.assertIn("C:\\", mounts)

    def test_export_report_json_roundtrip(self) -> None:
        """Reports serialize to readable JSON on disk."""
        report: Dict[str, Any] = {"alerts_count": 0, "results": []}
        target = self.dir_path / "report.json"
        export_report_json(report, str(target))
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), report)


class TestDiskUsageMonitorCli(unittest.TestCase):
    """CLI-level tests covering main() end to end."""

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        monitor_logger = logging.getLogger("DiskUsageMonitor")
        for handler in list(monitor_logger.handlers):
            handler.close()
            monitor_logger.removeHandler(handler)
        self.temp_dir.cleanup()

    @patch("main.get_mount_points", return_value=["/dev/sda1"])
    @patch("main.shutil.disk_usage")
    def test_main_exports_alert_report(
        self,
        mock_disk_usage: MagicMock,
        mock_mounts: MagicMock,
    ) -> None:
        """Low free space produces alerts and a JSON report file."""
        gb = 1024**3
        mock_disk_usage.return_value = shutil._ntuple_diskusage(
            100 * gb, 95 * gb, 5 * gb
        )
        log_path = self.dir_path / "run.log"
        report_path = self.dir_path / "report.json"

        stdout = io.StringIO()
        with redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "main.py",
                "-t",
                "10",
                "-l",
                str(log_path),
                "-o",
                str(report_path),
            ],
        ):
            main()

        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["threshold_free_percent"], 10.0)
        self.assertEqual(report["alerts_count"], 1)
        self.assertEqual(report["results"][0]["free_percent"], 5.0)
        self.assertIn("Report saved to", stdout.getvalue())
        self.assertIn("ALERT", log_path.read_text(encoding="utf-8"))

    @patch("main.get_mount_points", return_value=["/dev/sda1", "/dev/broken"])
    @patch("main.shutil.disk_usage")
    def test_main_continues_after_mount_failure(
        self,
        mock_disk_usage: MagicMock,
        mock_mounts: MagicMock,
    ) -> None:
        """One failing mount logs an error but does not abort the run."""
        gb = 1024**3

        def fake_disk_usage(mount_point: str) -> Any:
            if mount_point == "/dev/broken":
                raise OSError("unreachable mount")
            return shutil._ntuple_diskusage(100 * gb, 50 * gb, 50 * gb)

        mock_disk_usage.side_effect = fake_disk_usage

        stdout = io.StringIO()
        with redirect_stdout(stdout), patch("sys.argv", ["main.py", "-t", "90"]):
            main()

        output = stdout.getvalue()
        self.assertIn("Failed to check mount '/dev/broken'", output)
        self.assertIn("ALERT", output)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for disk-usage-monitor main module."""

import logging
import shutil
import unittest
from unittest.mock import MagicMock, patch

from main import check_disk_usage, evaluate_thresholds, get_mount_points


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


if __name__ == "__main__":
    unittest.main()

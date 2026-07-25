"""Unit tests for memory-usage-monitor main module."""

import csv
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from main import append_to_csv, get_memory_sample


class TestMemoryUsageMonitor(unittest.TestCase):
    """Test suite for memory usage monitor."""

    @patch("main.HAS_PSUTIL", True)
    @patch("main.psutil", create=True)
    def test_get_memory_sample(self, mock_psutil: MagicMock) -> None:
        """Test retrieving memory sample data."""
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=16 * 1024 * 1024 * 1024,
            used=8 * 1024 * 1024 * 1024,
            available=8 * 1024 * 1024 * 1024,
            percent=50.0,
        )
        mock_psutil.swap_memory.return_value = MagicMock(
            total=4 * 1024 * 1024 * 1024,
            used=1 * 1024 * 1024 * 1024,
            free=3 * 1024 * 1024 * 1024,
            percent=25.0,
        )

        sample = get_memory_sample()
        self.assertEqual(sample["ram_total_mb"], 16384.0)
        self.assertEqual(sample["ram_used_mb"], 8192.0)
        self.assertEqual(sample["ram_percent"], 50.0)
        self.assertEqual(sample["swap_percent"], 25.0)

    def test_csv_logging(self) -> None:
        """Test initializing and appending to CSV file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "memory_test.csv")
            sample = {
                "timestamp": "2026-07-24T12:00:00",
                "ram_total_mb": 8000.0,
                "ram_used_mb": 4000.0,
                "ram_free_mb": 4000.0,
                "ram_percent": 50.0,
                "swap_total_mb": 2000.0,
                "swap_used_mb": 500.0,
                "swap_free_mb": 1500.0,
                "swap_percent": 25.0,
            }

            append_to_csv(tmp_path, sample)

            with open(tmp_path, "r", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
                self.assertEqual(len(reader), 1)
                self.assertEqual(reader[0]["ram_percent"], "50.0")
                self.assertEqual(reader[0]["swap_percent"], "25.0")


if __name__ == "__main__":
    unittest.main()

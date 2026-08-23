"""Unit tests for memory-usage-monitor main module."""

import csv
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from main import append_to_csv, get_memory_sample, initialize_csv, main, run_monitor


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


class TestGetMemorySampleGuard(unittest.TestCase):
    """psutil availability guard for sampling."""

    def test_missing_psutil_raises_runtime_error(self) -> None:
        """Sampling without psutil raises a descriptive RuntimeError."""
        with patch("main.HAS_PSUTIL", False):
            with self.assertRaises(RuntimeError):
                get_memory_sample()


class TestCsvInitialization(unittest.TestCase):
    """Header creation and directory bootstrap of the CSV log."""

    def test_initialize_creates_parent_directories(self) -> None:
        """Missing parent directories are created before writing headers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "logs", "sub", "memory.csv")

            initialize_csv(target)

            self.assertTrue(os.path.exists(target))
            with open(target, "r", encoding="utf-8") as f:
                header = f.readline().strip()
            self.assertIn("timestamp", header)
            self.assertIn("swap_percent", header)

    def test_initialize_keeps_existing_file(self) -> None:
        """An existing log file is left untouched (no duplicate header)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "memory.csv")
            initialize_csv(target)
            append_to_csv(
                target,
                {
                    "timestamp": "T",
                    "ram_total_mb": 1.0,
                    "ram_used_mb": 1.0,
                    "ram_free_mb": 1.0,
                    "ram_percent": 1.0,
                    "swap_total_mb": 1.0,
                    "swap_used_mb": 1.0,
                    "swap_free_mb": 1.0,
                    "swap_percent": 1.0,
                },
            )
            initialize_csv(target)

            with open(target, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)


class TestRunMonitor(unittest.TestCase):
    """Sampling loop behaviour of run_monitor."""

    @staticmethod
    def _sample(percent: float) -> Dict[str, Any]:
        """Build a fully populated memory sample dictionary."""
        return {
            "timestamp": f"2026-08-01T00:00:0{int(percent)}",
            "ram_total_mb": 16000.0,
            "ram_used_mb": 8000.0,
            "ram_free_mb": 8000.0,
            "ram_percent": percent,
            "swap_total_mb": 4000.0,
            "swap_used_mb": 1000.0,
            "swap_free_mb": 3000.0,
            "swap_percent": percent / 2,
        }

    @patch("main.time.sleep")
    @patch("main.get_memory_sample")
    def test_fixed_count_writes_rows_and_stops(
        self, mock_sample: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """count=N appends exactly N rows then returns."""
        mock_sample.side_effect = [self._sample(10.0), self._sample(20.0)]
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "mem.csv")
            with redirect_stdout(stdout):
                run_monitor(log_path, interval=0.5, count=2)

            with open(log_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 2)
        self.assertEqual(mock_sleep.call_count, 1)
        self.assertIn("RAM: 10.0%", stdout.getvalue())
        self.assertIn("Swap:", stdout.getvalue())

    @patch("main.time.sleep", side_effect=KeyboardInterrupt)
    @patch("main.get_memory_sample")
    def test_keyboard_interrupt_stops_monitoring(
        self, mock_sample: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """Ctrl-C mid-loop keeps collected rows and exits gracefully."""
        mock_sample.return_value = self._sample(30.0)
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "mem.csv")
            with redirect_stdout(stdout):
                run_monitor(log_path, interval=1.0)  # count=None

            with open(log_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 1)
        self.assertIn("stopped by user", stdout.getvalue())


class TestMemoryUsageMonitorCli(unittest.TestCase):
    """CLI-level tests covering main() dispatch and guards."""

    @patch("main.HAS_PSUTIL", True)
    @patch("main.run_monitor")
    def test_main_dispatches_to_run_monitor(self, mock_run: MagicMock) -> None:
        """CLI flags map onto run_monitor keyword arguments."""
        with patch("sys.argv", ["main.py", "-o", "log.csv", "-i", "3", "-c", "7"]):
            main()

        mock_run.assert_called_once_with("log.csv", interval=3.0, count=7)

    def test_main_without_psutil_exits_with_error(self) -> None:
        """Missing psutil makes main() exit with status 1."""
        with patch("main.HAS_PSUTIL", False), patch("sys.argv", ["main.py"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for cpu-load-monitor main module."""

import unittest
from unittest.mock import MagicMock, patch

from main import generate_summary, sample_cpu


class TestCpuLoadMonitor(unittest.TestCase):
    """Test suite for CPU load monitor."""

    @patch("main.HAS_PSUTIL", True)
    @patch("main.psutil", create=True)
    def test_sample_cpu(self, mock_psutil: MagicMock) -> None:
        """Test sampling CPU metrics."""
        mock_psutil.cpu_percent.side_effect = [
            25.5,  # overall
            [20.0, 31.0],  # per core
        ]
        sample = sample_cpu(interval_sec=0.1)
        self.assertEqual(sample["overall_percent"], 25.5)
        self.assertEqual(sample["per_core_percent"], [20.0, 31.0])

    def test_generate_summary(self) -> None:
        """Test calculating summary metrics across multiple samples."""
        samples = [
            {
                "timestamp": "2026-07-24T12:00:00",
                "overall_percent": 10.0,
                "per_core_percent": [5.0, 15.0],
            },
            {
                "timestamp": "2026-07-24T12:00:05",
                "overall_percent": 50.0,
                "per_core_percent": [40.0, 60.0],
            },
            {
                "timestamp": "2026-07-24T12:00:10",
                "overall_percent": 30.0,
                "per_core_percent": [25.0, 35.0],
            },
        ]

        summary = generate_summary(samples)
        self.assertEqual(summary["total_samples"], 3)
        self.assertEqual(summary["average_overall_percent"], 30.0)
        self.assertEqual(summary["peak_overall_percent"], 50.0)
        self.assertEqual(summary["peak_timestamp"], "2026-07-24T12:00:05")

        core_0 = summary["per_core_summary"][0]
        self.assertEqual(core_0["core_id"], 0)
        self.assertEqual(core_0["avg_percent"], 23.33)
        self.assertEqual(core_0["peak_percent"], 40.0)


if __name__ == "__main__":
    unittest.main()

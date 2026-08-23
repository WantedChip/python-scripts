"""Unit tests for cpu-load-monitor main module."""

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from main import (
    export_json_report,
    generate_summary,
    main,
    print_console_summary,
    sample_cpu,
)


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


class TestSampleCpuLoadAverages(unittest.TestCase):
    """Load-average acquisition and psutil requirement of sample_cpu."""

    def test_sample_cpu_requires_psutil(self) -> None:
        """Missing psutil raises RuntimeError instead of crashing."""
        with patch("main.HAS_PSUTIL", False):
            with self.assertRaises(RuntimeError):
                sample_cpu()

    @patch("main.HAS_PSUTIL", True)
    @patch("main.psutil", create=True)
    def test_os_getloadavg_oserror_leaves_none(self, mock_psutil: MagicMock) -> None:
        """An OSError from os.getloadavg results in load_avg=None."""
        mock_psutil.cpu_percent.side_effect = [5.0, [5.0]]
        fake_os = MagicMock()
        fake_os.getloadavg.side_effect = OSError("unavailable")
        with patch("main.os", fake_os):
            sample = sample_cpu(interval_sec=0)
        self.assertIsNone(sample["load_avg"])

    @patch("main.HAS_PSUTIL", True)
    @patch("main.psutil", create=True)
    def test_psutil_getloadavg_fallback(self, mock_psutil: MagicMock) -> None:
        """Without os.getloadavg the psutil variant is used."""
        mock_psutil.cpu_percent.side_effect = [7.5, [1.0]]
        mock_psutil.getloadavg = MagicMock(side_effect=AttributeError)
        minimal_os = MagicMock(spec=["path"])
        with patch("main.os", minimal_os):
            sample = sample_cpu(interval_sec=0)
        self.assertIsNone(sample["load_avg"])
        self.assertEqual(sample["overall_percent"], 7.5)


class TestSummaryRendering(unittest.TestCase):
    """Console and JSON rendering of generated summaries."""

    def _summary_samples(self) -> List[Dict[str, Any]]:
        """Build two deterministic samples for reporting tests."""
        return [
            {
                "timestamp": "2026-08-01T09:00:00",
                "overall_percent": 20.0,
                "per_core_percent": [10.0, 30.0],
            },
            {
                "timestamp": "2026-08-01T09:00:05",
                "overall_percent": 80.0,
                "per_core_percent": [70.0, 90.0],
            },
        ]

    def test_generate_summary_empty_returns_empty_dict(self) -> None:
        """No samples produce an empty summary."""
        self.assertEqual(generate_summary([]), {})

    def test_print_console_summary_full_report(self) -> None:
        """The console table includes averages, peaks and core rows."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            print_console_summary(generate_summary(self._summary_samples()))
        output = stdout.getvalue()
        self.assertIn("CPU LOAD MONITOR SUMMARY REPORT", output)
        self.assertIn("Average CPU Load : 50.0%", output)
        self.assertIn("Peak CPU Load    : 80.0%", output)
        self.assertIn("Core 0", output)

    def test_print_console_summary_empty_data(self) -> None:
        """An empty summary prints a friendly notice."""
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            print_console_summary({})
        self.assertIn("No CPU data collected.", stdout.getvalue())

    def test_export_json_report_roundtrip(self) -> None:
        """export_json_report writes parseable JSON to disk."""
        payload: Dict[str, Any] = {"summary": {"a": 1}, "samples": [1, 2]}
        with TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "report.json"
            export_json_report(payload, str(target))
            data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data, payload)


class TestCpuLoadMonitorCli(unittest.TestCase):
    """CLI-level tests for main()."""

    @patch("main.HAS_PSUTIL", True)
    @patch("main.psutil", create=True)
    def test_main_collects_and_exports_report(self, mock_psutil: MagicMock) -> None:
        """main() samples N times, prints a report, exports JSON."""
        mock_psutil.cpu_percent.side_effect = [
            10.0,
            [11.0],
            20.0,
            [22.0],
        ]
        mock_psutil.getloadavg = MagicMock(return_value=(0.5, 0.4, 0.3))
        stdout = io.StringIO()
        with TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "cpu.json"
            with redirect_stdout(stdout), patch(
                "sys.argv", ["main.py", "-i", "0", "-c", "2", "-o", str(report_path)]
            ):
                main()

            data = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(len(data["samples"]), 2)
        self.assertEqual(data["summary"]["total_samples"], 2)
        self.assertEqual(data["summary"]["peak_overall_percent"], 20.0)
        self.assertIn("Sample 2/2", stdout.getvalue())
        self.assertIn("Exported JSON report", stdout.getvalue())

    def test_main_without_psutil_exits_with_error(self) -> None:
        """Missing psutil makes main() exit with status 1."""
        with patch("main.HAS_PSUTIL", False), patch("sys.argv", ["main.py"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()

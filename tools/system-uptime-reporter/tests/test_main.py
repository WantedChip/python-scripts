import time
import unittest
from unittest.mock import MagicMock, patch

from main import format_text_report, format_uptime_duration, get_system_uptime_report


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


if __name__ == "__main__":
    unittest.main()

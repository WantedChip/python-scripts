"""Unit tests for time-sync-auditor main.py."""

import json
import tempfile
import unittest
from pathlib import Path

from main import (
    evaluate_health,
    format_csv_report,
    format_table_report,
    main,
    parse_chrony_tracking,
    parse_json_input,
    parse_ntpstat,
)


class TestTimeSyncAuditor(unittest.TestCase):
    """Test suite for time-sync-auditor tool."""

    def test_parse_chrony_tracking(self) -> None:
        """Test parsing chrony tracking output format."""
        raw = """
Reference ID    : C1000001 (time.google.com)
Stratum         : 2
Ref time (UTC)  : Fri Jul 24 12:00:00 2026
System time     : 0.000123000 seconds slow of NTP time
Last offset     : +0.000012000 seconds
RMS offset      : 0.000050000 seconds
Frequency       : 12.345 ppm slow
Residual freq   : +0.001 ppm
Skew            : 0.012 ppm
Root delay      : 0.015000000 seconds
Root dispersion : 0.002000000 seconds
Update interval : 64.0 seconds
Leap status     : Normal
"""
        status = parse_chrony_tracking(raw, host="web-01")
        self.assertEqual(status.host, "web-01")
        self.assertEqual(status.service, "chrony")
        self.assertTrue(status.synced)
        self.assertEqual(status.stratum, 2)
        self.assertEqual(status.offset_ms, -0.123)
        self.assertEqual(status.frequency_ppm, 12.345)

    def test_parse_ntpstat(self) -> None:
        """Test parsing ntpstat output format."""
        raw = (
            "synchronised to NTP server (192.168.1.10) at stratum 3\n"
            "  time correct to within 15 ms"
        )
        status = parse_ntpstat(raw, host="db-01")
        self.assertTrue(status.synced)
        self.assertEqual(status.stratum, 3)
        self.assertEqual(status.offset_ms, 15.0)

        raw_unsync = "unsynchronised\n  time server re-starting"
        status_unsync = parse_ntpstat(raw_unsync, host="db-02")
        self.assertFalse(status_unsync.synced)

    def test_evaluate_health_thresholds(self) -> None:
        """Test health evaluation for warnings and critical drift."""
        raw = (
            "synchronised to NTP server (10.0.0.1) at stratum 5\n"
            "  time correct to within 50 ms"
        )
        st = parse_ntpstat(raw, host="app-01")
        evaluate_health(
            st,
            max_offset_warn_ms=10.0,
            max_offset_crit_ms=100.0,
            max_stratum_warn=4,
        )
        self.assertEqual(st.status, "WARNING")
        self.assertTrue(any("Elevated offset drift" in i for i in st.health_issues))
        self.assertTrue(any("High stratum" in i for i in st.health_issues))

    def test_parse_json_input(self) -> None:
        """Test parsing multi-host JSON dataset."""
        json_data = {
            "node1": (
                "Reference ID : C1000001\nStratum : 2\n"
                "System time : 0.001 seconds fast"
            ),
            "node2": "unsynchronised",
        }
        hosts = parse_json_input(json_data)
        self.assertEqual(len(hosts), 2)
        self.assertEqual(hosts[0].host, "node1")
        self.assertFalse(hosts[1].synced)

    def test_exporters(self) -> None:
        """Test table and CSV output rendering."""
        raw = (
            "synchronised to NTP server (10.0.0.1) at stratum 2\n"
            "  time correct to within 2 ms"
        )
        st = parse_ntpstat(raw, host="host1")
        st.status = "HEALTHY"
        table = format_table_report([st])
        self.assertIn("host1", table)
        self.assertIn("HEALTHY", table)

        csv_out = format_csv_report([st])
        self.assertIn("host1,ntpstat,True,HEALTHY", csv_out)

    def test_main_cli(self) -> None:
        """Test running main CLI with temporary log file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "chrony.log"
            out_file = Path(tmp_dir) / "report.json"

            raw_log = (
                "Reference ID : 10.0.0.1\nStratum : 2\n"
                "System time : 0.000100 seconds fast\n"
            )
            log_file.write_text(raw_log, encoding="utf-8")

            ret = main(
                [
                    "--file",
                    str(log_file),
                    "--host",
                    "test-node",
                    "--format",
                    "json",
                    "-o",
                    str(out_file),
                ]
            )
            self.assertEqual(ret, 0)
            self.assertTrue(out_file.exists())
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["host"], "test-node")


if __name__ == "__main__":
    unittest.main()

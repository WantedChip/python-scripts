"""Unit tests for time-sync-auditor main.py."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from main import (
    HostTimeStatus,
    detect_and_parse_log,
    evaluate_health,
    format_csv_report,
    format_table_report,
    main,
    parse_args,
    parse_chrony_tracking,
    parse_json_input,
    parse_ntpq,
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


NTPQ_PEERS = (
    "     remote           refid      st t when poll reach   delay"
    "   offset  jitter\n"
    "==============================================================================\n"
    " 10.0.0.2        .INIT.          16 u    -   64    0    0.000"
    "    0.000   0.000\n"
    "*time.example.com 10.0.0.1        2 u   32   64  377    0.421"
    "   -0.105   0.012\n"
)


class TestParserEdgeCases(unittest.TestCase):
    """Additional parser coverage for chrony/ntpq variants and detection."""

    def test_parse_chrony_tracking_unsynced_reference(self) -> None:
        raw = "Reference ID : 00000000 ()\nStratum : 16\n"
        status = parse_chrony_tracking(raw, host="lonely-01")
        self.assertFalse(status.synced)

    def test_parse_ntpq_active_peer_row(self) -> None:
        status = parse_ntpq(NTPQ_PEERS, host="edge-01")
        self.assertTrue(status.synced)
        self.assertEqual(status.service, "ntpq")
        self.assertEqual(status.reference_source, "time.example.com")
        self.assertEqual(status.stratum, 2)
        self.assertAlmostEqual(status.offset_ms, -0.105)
        self.assertAlmostEqual(status.root_delay_ms, 0.012)

    def test_parse_ntpq_without_active_peer_is_critical(self) -> None:
        status = parse_ntpq(
            "     remote           refid      st t when poll reach\n", host="edge-02"
        )
        self.assertFalse(status.synced)
        self.assertEqual(status.status, "CRITICAL")
        self.assertIn("No active peer", status.health_issues[0])

    def test_detect_and_parse_log_routes_by_content(self) -> None:
        chrony = detect_and_parse_log("Reference ID : C0A8010A\nStratum : 3", host="h1")
        self.assertEqual(chrony.service, "chrony")

        ntp = detect_and_parse_log(
            "synchronised to NTP server (10.0.0.9) at stratum 2", host="h2"
        )
        self.assertEqual(ntp.service, "ntpstat")

        peers = detect_and_parse_log(
            "     remote           refid      st t when poll reach\n" + NTPQ_PEERS,
            host="h3",
        )
        self.assertEqual(peers.service, "ntpq")

        unknown = detect_and_parse_log("total garbage output", host="h4")
        self.assertEqual(unknown.service, "unknown")
        self.assertFalse(unknown.synced)
        self.assertIn("Unrecognized", unknown.health_issues[0])

    def test_evaluate_health_critical_and_drift_paths(self) -> None:
        unsynced = HostTimeStatus(host="u1", service="ntpstat", synced=False)
        evaluate_health(unsynced)
        self.assertEqual(unsynced.status, "CRITICAL")
        self.assertIn("Host time is unsynchronized", unsynced.health_issues)

        drift = HostTimeStatus(
            host="u2", service="chrony", synced=True, offset_ms=150.0
        )
        evaluate_health(drift, max_offset_crit_ms=100.0)
        self.assertEqual(drift.status, "CRITICAL")
        self.assertIn("Critical offset drift", drift.health_issues[0])

        tall = HostTimeStatus(host="u3", service="chrony", synced=True, stratum=12)
        evaluate_health(tall, max_stratum_crit=10)
        self.assertEqual(tall.status, "CRITICAL")
        self.assertIn("Critical stratum height", tall.health_issues[0])

        freq = HostTimeStatus(
            host="u4", service="chrony", synced=True, frequency_ppm=250.0
        )
        evaluate_health(freq, max_drift_ppm=100.0)
        self.assertEqual(freq.status, "WARNING")
        self.assertIn("Excessive frequency drift", freq.health_issues[0])


class TestJsonInputVariants(unittest.TestCase):
    """Coverage for structured JSON datasets and table issue rendering."""

    def test_parse_json_input_dict_of_dicts_with_service_override(self) -> None:
        payload: Dict[str, Any] = {
            "node-a": {
                "output": "Reference ID : C0A80165\nStratum : 2",
                "service": "chronyd",
            },
            "node-b": {"raw": "unsynchronised"},
        }
        hosts = parse_json_input(payload)
        self.assertEqual(len(hosts), 2)
        self.assertEqual(hosts[0].host, "node-a")
        self.assertEqual(hosts[0].service, "chronyd")
        self.assertTrue(hosts[0].synced)
        self.assertFalse(hosts[1].synced)

    def test_parse_json_input_list_entries_with_hostname_fallbacks(self) -> None:
        payload: list[Any] = [
            {"host": "web-01", "output": "unsynchronised"},
            {"hostname": "web-02", "raw": "Reference ID : 10.0.0.7\nStratum : 2"},
            {"output": ""},
        ]
        hosts = parse_json_input(payload)
        self.assertEqual([h.host for h in hosts], ["web-01", "web-02", "host_3"])

    def test_format_table_report_lists_health_issues(self) -> None:
        bad = HostTimeStatus(
            host="bad-host",
            service="chrony",
            synced=False,
            status="CRITICAL",
            health_issues=["Host time is unsynchronized"],
        )
        table = format_table_report([bad])
        self.assertIn("bad-host", table)
        self.assertIn("Issue: Host time is unsynchronized", table)


class TestTimeSyncCliPaths(unittest.TestCase):
    """CLI error paths, format selection, and critical exit codes."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_main_requires_file_or_json_input(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ret = main([])
        self.assertEqual(ret, 1)
        self.assertIn("--file or --json-input", err.getvalue())

    def test_main_missing_file_returns_error(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ret = main(["--file", str(self.root / "nope.log")])
        self.assertEqual(ret, 1)
        self.assertIn("Input file not found", err.getvalue())

    def test_main_invalid_json_returns_error(self) -> None:
        bad_json = self.root / "broken.json"
        bad_json.write_text("{not valid json", encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ret = main(["--json-input", str(bad_json)])
        self.assertEqual(ret, 1)
        self.assertIn("Error parsing JSON input", err.getvalue())

    def test_main_missing_json_file_returns_error(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ret = main(["--json-input", str(self.root / "ghost.json")])
        self.assertEqual(ret, 1)
        self.assertIn("JSON input file not found", err.getvalue())

    def test_main_csv_format_to_stdout(self) -> None:
        log = self.root / "c.log"
        log.write_text(
            "Reference ID : 10.0.0.1\nStratum : 2\n"
            "System time : 0.001 seconds fast\n",
            encoding="utf-8",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["--file", str(log), "--format", "csv"])
        self.assertEqual(ret, 0)
        self.assertIn("host,service,synced,status", buf.getvalue())
        self.assertIn("localhost,chrony,True", buf.getvalue())

    def test_main_table_format_to_stdout(self) -> None:
        log = self.root / "n.log"
        log.write_text(
            "synchronised to NTP server (10.0.0.5) at stratum 2\n"
            "  time correct to within 3 ms",
            encoding="utf-8",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["--file", str(log), "--format", "table"])
        self.assertEqual(ret, 0)
        self.assertIn("TIME SYNCHRONIZATION AUDIT REPORT", buf.getvalue())

    def test_main_exits_two_when_any_host_is_critical(self) -> None:
        dataset = self.root / "fleet.json"
        dataset.write_text(
            json.dumps({"node-x": {"output": "unsynchronised"}}),
            encoding="utf-8",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["--json-input", str(dataset)])
        self.assertEqual(ret, 2)
        self.assertIn("CRITICAL", buf.getvalue())

    def test_parse_args_threshold_defaults(self) -> None:
        parsed = parse_args(["--file", "x.log"])
        self.assertEqual(parsed.max_offset_warn, 10.0)
        self.assertEqual(parsed.max_offset_crit, 100.0)
        self.assertEqual(parsed.max_stratum_warn, 4)
        self.assertEqual(parsed.max_drift_ppm, 100.0)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Local Network Device Monitor."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Workaround for hyphenated folder module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error,wrong-import-position
import device_monitor  # noqa: E402


class TestDeviceMonitor(unittest.TestCase):
    """Test suite for device_monitor functions."""

    def test_get_oui(self) -> None:
        """Test MAC OUI prefix lookup."""
        self.assertEqual(
            device_monitor.get_oui("b8:27:eb:11:22:33"), "Raspberry Pi Foundation"
        )
        self.assertEqual(
            device_monitor.get_oui("B8-27-EB-AA-BB-CC"), "Raspberry Pi Foundation"
        )
        self.assertEqual(device_monitor.get_oui("00:00:00:11:22:33"), "Unknown")

    @patch("socket.socket")
    def test_get_local_ip(self, mock_socket: MagicMock) -> None:
        """Test local IP retrieval."""
        mock_instance = MagicMock()
        mock_instance.getsockname.return_value = ("192.168.1.50", 12345)
        mock_socket.return_value = mock_instance

        self.assertEqual(device_monitor.get_local_ip(), "192.168.1.50")

    def test_get_subnet_ips_with_argument(self) -> None:
        """Test subnet generator with manual prefix."""
        ips = device_monitor.get_subnet_ips("10.0.0")
        self.assertEqual(len(ips), 254)
        self.assertEqual(ips[0], "10.0.0.1")
        self.assertEqual(ips[-1], "10.0.0.254")

    @patch("subprocess.run")
    def test_ping_host(self, mock_run: MagicMock) -> None:
        """Test ping exit code conversion."""
        # Success exit code 0
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(device_monitor.ping_host("192.168.1.1"))

        # Failure exit code 1
        mock_run.return_value = MagicMock(returncode=1)
        self.assertFalse(device_monitor.ping_host("192.168.1.1"))

    @patch("subprocess.run")
    def test_parse_arp_table_windows(self, mock_run: MagicMock) -> None:
        """Test parsing Windows arp -a table output."""
        # Setup system platform mock
        with patch("sys.platform", "win32"):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=(
                    "Interface: 192.168.1.50 --- 0x5\n"
                    "  Internet Address      Physical Address      Type\n"
                    "  192.168.1.1           b8-27-eb-11-22-33     dynamic\n"
                    "  192.168.1.255         ff-ff-ff-ff-ff-ff     static\n"
                    "  224.0.0.22            01-00-5e-00-00-16     static\n"
                ),
            )
            devices = device_monitor.parse_arp_table()
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0], ("192.168.1.1", "b8:27:eb:11:22:33"))

    def test_update_monitor(self) -> None:
        """Test tracking logic (joins, leaves, and ip changes)."""
        state = {"devices": {}, "history": []}

        # Scan 1: Discovery of Device A
        active_1 = [("192.168.1.10", "00:17:88:aa:bb:cc")]
        changes_1 = device_monitor.update_monitor(state, active_1)
        self.assertEqual(len(changes_1), 1)
        self.assertEqual(changes_1[0]["event"], "joined")
        self.assertEqual(changes_1[0]["mac"], "00:17:88:aa:bb:cc")
        self.assertEqual(state["devices"]["00:17:88:aa:bb:cc"]["status"], "online")

        # Scan 2: Device A stays online, no changes
        changes_2 = device_monitor.update_monitor(state, active_1)
        self.assertEqual(len(changes_2), 0)

        # Scan 3: Device A moves IP
        active_3 = [("192.168.1.20", "00:17:88:aa:bb:cc")]
        changes_3 = device_monitor.update_monitor(state, active_3)
        self.assertEqual(len(changes_3), 1)
        self.assertEqual(changes_3[0]["event"], "ip_changed")
        self.assertEqual(changes_3[0]["old_ip"], "192.168.1.10")
        self.assertEqual(changes_3[0]["new_ip"], "192.168.1.20")

        # Scan 4: Device A leaves (offline)
        active_4 = []
        changes_4 = device_monitor.update_monitor(state, active_4)
        self.assertEqual(len(changes_4), 1)
        self.assertEqual(changes_4[0]["event"], "left")
        self.assertEqual(state["devices"]["00:17:88:aa:bb:cc"]["status"], "offline")

    def test_state_load_save(self) -> None:
        """Test loading and saving of state."""
        state = {
            "devices": {"00:11:32:00:00:00": {"ip": "192.168.1.5", "status": "online"}},
            "history": [],
        }
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
            temp_path = f.name

        try:
            device_monitor.save_state(temp_path, state)
            loaded = device_monitor.load_state(temp_path)
            self.assertIn("00:11:32:00:00:00", loaded["devices"])
            self.assertEqual(
                loaded["devices"]["00:11:32:00:00:00"]["ip"], "192.168.1.5"
            )
        finally:
            os.remove(temp_path)

    @patch("socket.socket")
    def test_get_local_ip_failure(self, mock_socket: MagicMock) -> None:
        """Test get_local_ip returns None on socket exception."""
        mock_instance = MagicMock()
        mock_instance.connect.side_effect = Exception("Network unreachable")
        mock_socket.return_value = mock_instance
        self.assertIsNone(device_monitor.get_local_ip())

    @patch("device_monitor.get_local_ip")
    def test_get_subnet_ips_auto_failure(self, mock_get_ip: MagicMock) -> None:
        """Test get_subnet_ips returns empty list when auto-detect IP fails."""
        mock_get_ip.return_value = None
        self.assertEqual(device_monitor.get_subnet_ips(), [])

        mock_get_ip.return_value = "badip"
        self.assertEqual(device_monitor.get_subnet_ips(), [])

    @patch("subprocess.run")
    def test_ping_host_unix_and_fail(self, mock_run: MagicMock) -> None:
        """Test ping_host with POSIX arguments and exceptions."""
        with patch("sys.platform", "linux"):
            mock_run.return_value = MagicMock(returncode=0)
            self.assertTrue(device_monitor.ping_host("192.168.1.1"))

        # subprocess raises exception
        mock_run.side_effect = subprocess.SubprocessError("Failed to start")
        self.assertFalse(device_monitor.ping_host("192.168.1.1"))

    @patch("subprocess.run")
    def test_parse_arp_table_unix(self, mock_run: MagicMock) -> None:
        """Test parsing POSIX arp -an output."""
        with patch("sys.platform", "linux"):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=(
                    "192.168.1.1 b8:27:eb:11:22:33\n"
                    "192.168.1.2 c8-d7-19-11-22-33\n"
                    "224.0.0.1 01:00:5e:00:00:01\n"
                ),
            )
            devices = device_monitor.parse_arp_table()
            self.assertEqual(len(devices), 2)
            self.assertEqual(devices[0], ("192.168.1.1", "b8:27:eb:11:22:33"))
            self.assertEqual(devices[1], ("192.168.1.2", "c8:d7:19:11:22:33"))

    @patch("subprocess.run")
    def test_parse_arp_table_exception(self, mock_run: MagicMock) -> None:
        """Test parse_arp_table returns empty list on exception."""
        mock_run.side_effect = subprocess.SubprocessError("Failed to execute")
        self.assertEqual(device_monitor.parse_arp_table(), [])

    def test_load_state_corrupted(self) -> None:
        """Test load_state returns default on corrupted json."""
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write("invalid json {")
            temp_path = tmp.name

        try:
            state = device_monitor.load_state(temp_path)
            self.assertEqual(state, {"devices": {}, "history": []})
        finally:
            os.remove(temp_path)

        # File does not exist
        self.assertEqual(
            device_monitor.load_state("nonexistent_state.json"),
            {"devices": {}, "history": []},
        )

    def test_save_state_exception(self) -> None:
        """Test save_state handles exception gracefully."""
        # Empty dictionary state writing to a read-only path
        device_monitor.save_state("", {})

    def test_update_monitor_history_prune(self) -> None:
        """Test update_monitor prunes history when history_limit is exceeded."""
        state = {
            "devices": {},
            "history": [
                {
                    "timestamp": "2026-01-01T00:00:00",
                    "event": "joined",
                    "mac": "00:00:00:00:00:00",
                    "ip": "1.1.1.1",
                }
            ],
        }
        active = [("192.168.1.10", "b8:27:eb:11:22:33")]

        # history limit is 1, so the join of Device B should prune the
        # previous history item
        device_monitor.update_monitor(state, active, history_limit=1)
        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["mac"], "b8:27:eb:11:22:33")

        # Test device rejoined (moving from offline to online)
        state_rejoin = {
            "devices": {
                "b8:27:eb:11:22:33": {
                    "ip": "192.168.1.10",
                    "status": "offline",
                    "vendor": "Raspberry Pi",
                }
            },
            "history": [],
        }
        changes = device_monitor.update_monitor(state_rejoin, active)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["event"], "joined")
        self.assertEqual(
            state_rejoin["devices"]["b8:27:eb:11:22:33"]["status"], "online"
        )

    def test_print_report(self) -> None:
        """Test print_report prints correct logs without errors."""
        import io
        from unittest.mock import patch

        state = {
            "devices": {
                "b8:27:eb:11:22:33": {
                    "ip": "192.168.1.10",
                    "first_seen": "2026-01-01T00:00:00",
                    "last_seen": "2026-01-01T00:00:00",
                    "name": "Device 10",
                    "vendor": "Raspberry Pi",
                    "status": "online",
                }
            },
            "history": [],
        }
        changes = [
            {
                "event": "joined",
                "ip": "192.168.1.10",
                "mac": "b8:27:eb:11:22:33",
                "vendor": "Raspberry Pi",
            },
            {
                "event": "left",
                "ip": "192.168.1.10",
                "mac": "b8:27:eb:11:22:33",
                "vendor": "Raspberry Pi",
            },
            {
                "event": "ip_changed",
                "mac": "b8:27:eb:11:22:33",
                "old_ip": "192.168.1.5",
                "new_ip": "192.168.1.10",
            },
        ]

        f = io.StringIO()
        with patch("sys.stdout", new=f):
            device_monitor.print_report(state, changes)

        output = f.getvalue()
        self.assertIn("LOCAL NETWORK MONITOR REPORT", output)
        self.assertIn("ONLINE DEVICES", output)
        self.assertIn("EVENTS IN THIS SCAN", output)

    @patch("device_monitor.ping_sweep")
    @patch("device_monitor.parse_arp_table")
    @patch("device_monitor.load_state")
    @patch("device_monitor.save_state")
    def test_main_cli(
        self,
        mock_save: MagicMock,
        mock_load: MagicMock,
        mock_arp: MagicMock,
        mock_ping: MagicMock,
    ) -> None:
        """Test main CLI entry point."""
        mock_arp.return_value = [("192.168.1.10", "b8:27:eb:11:22:33")]
        mock_load.return_value = {"devices": {}, "history": []}

        import io
        from unittest.mock import patch

        f = io.StringIO()
        with patch("sys.stdout", new=f):
            device_monitor.main(
                ["-s", "192.168.1", "--state-file", "dummy.json", "--json-output"]
            )

        self.assertIn('"devices"', f.getvalue())
        mock_ping.assert_called_once()
        mock_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()

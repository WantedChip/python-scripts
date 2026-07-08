"""Unit tests for Process Port Inspector."""

import collections
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Workaround for hyphenated folder module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error,wrong-import-position
import port_inspector

# Define connection named tuple similar to psutil's structure
sconn = collections.namedtuple("sconn", ["fd", "family", "type", "laddr", "raddr", "status", "pid"])
addr = collections.namedtuple("addr", ["ip", "port"])


class TestPortInspector(unittest.TestCase):
    """Test suite for port_inspector functions."""

    @patch("psutil.Process")
    def test_get_process_info_success(self, mock_process_cls: MagicMock) -> None:
        """Test process info retrieval when successful."""
        mock_proc = MagicMock()
        mock_proc.name.return_value = "python.exe"
        mock_proc.exe.return_value = "C:\\Python\\python.exe"
        mock_proc.username.return_value = "Administrator"
        mock_proc.status.return_value = "running"
        mock_process_cls.return_value = mock_proc

        info = port_inspector.get_process_info(1234)
        self.assertEqual(info["pid"], 1234)
        self.assertEqual(info["name"], "python.exe")
        self.assertEqual(info["path"], "C:\\Python\\python.exe")
        self.assertEqual(info["user"], "Administrator")
        self.assertEqual(info["status"], "running")

    @patch("psutil.net_connections")
    @patch("port_inspector.get_process_info")
    def test_list_connections(
        self, mock_get_info: MagicMock, mock_net_conns: MagicMock
    ) -> None:
        """Test listing and filtering of ports."""
        import socket

        # Setup mock connections
        conn1 = sconn(
            fd=-1,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            laddr=addr(ip="127.0.0.1", port=8080),
            raddr=None,
            status="LISTEN",
            pid=1001,
        )
        conn2 = sconn(
            fd=-1,
            family=socket.AF_INET,
            type=socket.SOCK_DGRAM,
            laddr=addr(ip="0.0.0.0", port=53),
            raddr=None,
            status="NONE",
            pid=1002,
        )
        mock_net_conns.return_value = [conn1, conn2]

        # Setup process info mock
        mock_get_info.side_effect = lambda pid: {
            1001: {
                "pid": 1001,
                "name": "webserver",
                "path": "/bin/webserver",
                "user": "root",
                "status": "running",
            },
            1002: {
                "pid": 1002,
                "name": "dnsmasq",
                "path": "/bin/dnsmasq",
                "user": "nobody",
                "status": "running",
            },
        }[pid]

        # Fetch TCP and UDP
        all_conns = port_inspector.list_connections(protocol="all")
        self.assertEqual(len(all_conns), 2)

        # Filter by port
        port_8080_conns = port_inspector.list_connections(port_filter=8080)
        self.assertEqual(len(port_8080_conns), 1)
        self.assertEqual(port_8080_conns[0]["pid"], 1001)
        self.assertEqual(port_8080_conns[0]["process_name"], "webserver")

    @patch("psutil.Process")
    @patch("psutil.wait_procs")
    def test_terminate_process(self, mock_wait_procs: MagicMock, mock_process_cls: MagicMock) -> None:
        """Test soft and force termination of processes."""
        mock_proc = MagicMock()
        mock_process_cls.return_value = mock_proc

        # Mock wait_procs to return that the process terminated (was gone)
        mock_wait_procs.return_value = ([mock_proc], [])

        # Soft terminate
        result = port_inspector.terminate_process(9999, force=False)
        self.assertTrue(result)
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()

        # Reset mocks
        mock_proc.reset_mock()

        # Force terminate
        result_force = port_inspector.terminate_process(9999, force=True)
        self.assertTrue(result_force)
        mock_proc.terminate.assert_not_called()
        mock_proc.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()

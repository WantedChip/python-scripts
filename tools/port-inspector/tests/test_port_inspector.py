"""Unit tests for Process Port Inspector."""

import collections
import os
import sys
import io
import unittest
import psutil
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


    def test_get_process_info_system_idle(self) -> None:
        """Test get_process_info for system idle process (PID 0)."""
        info = port_inspector.get_process_info(0)
        self.assertEqual(info["name"], "System Idle Process")

    @patch("psutil.Process")
    def test_get_process_info_access_denied(self, mock_process_cls: MagicMock) -> None:
        """Test get_process_info when permissions are denied."""
        mock_proc = MagicMock()
        mock_proc.name.side_effect = psutil.AccessDenied()
        mock_process_cls.return_value = mock_proc

        info = port_inspector.get_process_info(1111)
        self.assertEqual(info["name"], "Access Denied")

        # Test partial access denied
        mock_proc2 = MagicMock()
        mock_proc2.name.return_value = "system"
        mock_proc2.exe.side_effect = psutil.AccessDenied()
        mock_proc2.username.side_effect = psutil.AccessDenied()
        mock_proc2.status.return_value = "running"
        mock_process_cls.return_value = mock_proc2

        info2 = port_inspector.get_process_info(2222)
        self.assertEqual(info2["name"], "system")
        self.assertEqual(info2["path"], "Access Denied")
        self.assertEqual(info2["user"], "Access Denied")

    @patch("psutil.Process")
    def test_get_process_info_no_such_process(self, mock_process_cls: MagicMock) -> None:
        """Test get_process_info when process does not exist."""
        mock_process_cls.side_effect = psutil.NoSuchProcess(3333)
        info = port_inspector.get_process_info(3333)
        self.assertEqual(info["name"], "No Such Process")

    @patch("psutil.net_connections")
    def test_list_connections_exceptions(self, mock_net_conns: MagicMock) -> None:
        """Test list_connections returns empty list on AccessDenied."""
        mock_net_conns.side_effect = PermissionError("Permission Denied")
        self.assertEqual(port_inspector.list_connections(), [])

    def test_terminate_process_system_idle(self) -> None:
        """Test terminating PID 0 is prevented."""
        self.assertFalse(port_inspector.terminate_process(0))

    @patch("psutil.Process")
    @patch("psutil.wait_procs")
    def test_terminate_process_alive_soft_failure(
        self, mock_wait_procs: MagicMock, mock_process_cls: MagicMock
    ) -> None:
        """Test soft termination fails and prompt/force kill is executed."""
        mock_proc = MagicMock()
        mock_process_cls.return_value = mock_proc
        
        # Soft terminate returns alive process, force kill succeeds (returns gone)
        mock_wait_procs.side_effect = [([], [mock_proc]), ([mock_proc], [])]

        with patch("builtins.input", return_value="y") as mock_input:
            result = port_inspector.terminate_process(9999, force=False)
            self.assertTrue(result)
            mock_input.assert_called_once()

        # Mock user says no to force kill
        mock_wait_procs.side_effect = [([], [mock_proc])]
        with patch("builtins.input", return_value="n") as mock_input:
            result_no = port_inspector.terminate_process(9999, force=False)
            self.assertFalse(result_no)

    @patch("psutil.Process")
    def test_terminate_process_exceptions(self, mock_process_cls: MagicMock) -> None:
        """Test terminate_process handles NoSuchProcess and AccessDenied."""
        mock_process_cls.side_effect = psutil.NoSuchProcess(1234)
        self.assertTrue(port_inspector.terminate_process(1234))

        mock_process_cls.side_effect = psutil.AccessDenied()
        self.assertFalse(port_inspector.terminate_process(1234))

    def test_print_table(self) -> None:
        """Test print_table outputs correct formatted text."""
        import io
        from unittest.mock import patch

        f = io.StringIO()
        with patch("sys.stdout", new=f):
            port_inspector.print_table([])
        self.assertIn("No matching connections found", f.getvalue())

        f2 = io.StringIO()
        conns = [
            {
                "protocol": "SOCK_STREAM",
                "local_address": "127.0.0.1:80",
                "remote_address": "-",
                "state": "LISTEN",
                "pid": 80,
                "process_name": "httpd",
                "process_user": "root",
            }
        ]
        with patch("sys.stdout", new=f2):
            port_inspector.print_table(conns)
        self.assertIn("TCP", f2.getvalue())
        self.assertIn("127.0.0.1:80", f2.getvalue())

    @patch("port_inspector.list_connections")
    @patch("port_inspector.get_process_info")
    @patch("port_inspector.terminate_process")
    def test_main_cli(
        self, mock_terminate: MagicMock, mock_get_info: MagicMock, mock_list: MagicMock
    ) -> None:
        """Test port_inspector CLI parser and logic scenarios."""
        # 1. Error: --kill requires -p
        with self.assertRaises(SystemExit) as exc:
            port_inspector.main(["--kill"])
        self.assertEqual(exc.exception.code, 1)

        # 2. Kill success with force
        mock_list.return_value = [
            {
                "pid": 4444,
                "protocol": "SOCK_STREAM",
                "local_address": "127.0.0.1:80",
                "remote_address": "-",
                "state": "LISTEN",
                "process_name": "httpd",
                "process_user": "root",
            }
        ]
        mock_get_info.return_value = {
            "name": "httpd",
            "path": "/bin/httpd",
        }
        mock_terminate.return_value = True

        with self.assertRaises(SystemExit) as exc:
            port_inspector.main(["-p", "80", "--kill", "--force"])
        self.assertEqual(exc.exception.code, 0)
        mock_terminate.assert_called_with(4444, force=True)


        # Let's run it directly
        f2 = io.StringIO()
        with patch("sys.stdout", new=f2):
            port_inspector.main(["-p", "80", "--json-output"])
        self.assertIn('"pid": 4444', f2.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Port Availability Checker."""

import contextlib
import io
import json
import socket
import unittest
from unittest.mock import MagicMock, patch

from main import (
    check_tcp_port,
    check_udp_port,
    format_summary_table,
    main,
    parse_args,
    parse_port_specs,
    scan_ports,
)


class TestPortAvailabilityChecker(unittest.TestCase):

    def test_parse_port_specs(self) -> None:
        self.assertEqual(parse_port_specs("80,443"), [80, 443])
        self.assertEqual(parse_port_specs("8000-8003"), [8000, 8001, 8002, 8003])
        self.assertEqual(
            parse_port_specs("22, 8000-8002, 443"),
            [22, 443, 8000, 8001, 8002],
        )

    def test_parse_port_specs_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_port_specs("8000-7000")
        with self.assertRaises(ValueError):
            parse_port_specs("70000")

    @patch("socket.socket")
    def test_check_tcp_port_open(self, mock_socket_cls: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__.return_value = mock_sock
        mock_sock.connect_ex.return_value = 0

        res = check_tcp_port("127.0.0.1", 80)
        self.assertTrue(res["open"])
        self.assertEqual(res["status"], "OPEN")

    @patch("socket.socket")
    def test_check_tcp_port_closed(self, mock_socket_cls: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__.return_value = mock_sock
        mock_sock.connect_ex.return_value = 111  # Connection refused

        res = check_tcp_port("127.0.0.1", 80)
        self.assertFalse(res["open"])
        self.assertEqual(res["status"], "CLOSED")

    @patch("socket.socket")
    def test_check_udp_port_open(self, mock_socket_cls: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__.return_value = mock_sock
        mock_sock.recvfrom.return_value = (b"reply", ("127.0.0.1", 53))

        res = check_udp_port("127.0.0.1", 53)
        self.assertTrue(res["open"])
        self.assertEqual(res["status"], "OPEN")

    def test_format_summary_table(self) -> None:
        results = [
            {"host": "localhost", "port": 80, "protocol": "TCP", "status": "OPEN"},
            {"host": "localhost", "port": 443, "protocol": "TCP", "status": "CLOSED"},
        ]
        table = format_summary_table(results)
        self.assertIn("localhost", table)
        self.assertIn("OPEN", table)
        self.assertIn("CLOSED", table)


class TestPortCheckerEdgeCases(unittest.TestCase):
    """Edge-case and CLI coverage for the port scanner."""

    def test_parse_port_specs_ignores_empty_segments(self) -> None:
        self.assertEqual(parse_port_specs("80,,443,"), [80, 443])

    def test_parse_port_specs_rejects_out_of_range_bounds(self) -> None:
        with self.assertRaises(ValueError):
            parse_port_specs("0-10")
        with self.assertRaises(ValueError):
            parse_port_specs("80-65536")

    @patch("socket.socket")
    def test_check_tcp_port_socket_error(self, mock_socket_cls: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__.return_value = mock_sock
        mock_sock.connect_ex.side_effect = OSError("network unreachable")

        res = check_tcp_port("10.255.255.1", 80)
        self.assertFalse(res["open"])
        self.assertEqual(res["status"], "CLOSED")
        self.assertIn("network unreachable", res["error"])

    @patch("socket.socket")
    def test_check_udp_port_timeout_is_open_or_filtered(
        self, mock_socket_cls: MagicMock
    ) -> None:
        """A UDP probe timeout means the port is open or filtered, not closed."""
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__.return_value = mock_sock
        mock_sock.recvfrom.side_effect = socket.timeout

        res = check_udp_port("127.0.0.1", 53)
        self.assertTrue(res["open"])
        self.assertEqual(res["status"], "OPEN|FILTERED")
        self.assertIn("No response", res["error"])

    @patch("socket.socket")
    def test_check_udp_port_send_error(self, mock_socket_cls: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__.return_value = mock_sock
        mock_sock.sendto.side_effect = OSError("send failure")

        res = check_udp_port("127.0.0.1", 53)
        self.assertFalse(res["open"])
        self.assertEqual(res["status"], "CLOSED")
        self.assertIn("send failure", res["error"])

    @patch("main.check_udp_port")
    @patch("main.check_tcp_port")
    def test_scan_ports_dispatches_and_sorts(
        self, mock_tcp: MagicMock, mock_udp: MagicMock
    ) -> None:
        mock_tcp.side_effect = lambda h, p, t: {
            "host": h,
            "port": p,
            "protocol": "TCP",
            "status": "OPEN",
            "open": True,
            "error": None,
        }
        results = scan_ports("localhost", [443, 80, 22], protocol="TCP", timeout=1.0)
        self.assertEqual([r["port"] for r in results], [22, 80, 443])
        self.assertEqual(mock_tcp.call_count, 3)
        mock_udp.assert_not_called()

        # Non-TCP protocols must route to the UDP checker.
        mock_udp.return_value = {"port": 53}
        scan_ports("localhost", [53], protocol="UDP", timeout=1.0)
        mock_udp.assert_called_once()

    def test_parse_args_defaults(self) -> None:
        parsed = parse_args(["example.com"])
        self.assertEqual(parsed.host, "example.com")
        self.assertEqual(parsed.ports, "80,443,22,8080")
        self.assertEqual(parsed.protocol, "TCP")
        self.assertEqual(parsed.timeout, 2.0)
        self.assertFalse(parsed.json)

    def test_main_invalid_port_spec_returns_error(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            ret = main(["example.com", "-p", "99999"])
        self.assertEqual(ret, 1)
        self.assertIn("Error:", buf.getvalue())

    @patch("main.scan_ports")
    def test_main_renders_summary_table(self, mock_scan: MagicMock) -> None:
        mock_scan.return_value = [
            {
                "host": "db.local",
                "port": 5432,
                "protocol": "TCP",
                "status": "OPEN",
                "open": True,
                "error": None,
            },
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["db.local", "-p", "5432"])
        self.assertEqual(ret, 0)
        self.assertIn("db.local", buf.getvalue())
        self.assertIn("5432", buf.getvalue())

    @patch("main.scan_ports")
    def test_main_json_output(self, mock_scan: MagicMock) -> None:
        mock_scan.return_value = [
            {
                "host": "db.local",
                "port": 5432,
                "protocol": "TCP",
                "status": "CLOSED",
                "open": False,
                "error": "refused",
            },
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["db.local", "-p", "5432", "--json"])
        self.assertEqual(ret, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload[0]["port"], 5432)
        self.assertEqual(payload[0]["status"], "CLOSED")


if __name__ == "__main__":
    unittest.main()

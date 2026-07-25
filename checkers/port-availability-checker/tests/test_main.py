"""Unit tests for Port Availability Checker."""

import unittest
from unittest.mock import MagicMock, patch

from main import check_tcp_port, check_udp_port, format_summary_table, parse_port_specs


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


if __name__ == "__main__":
    unittest.main()

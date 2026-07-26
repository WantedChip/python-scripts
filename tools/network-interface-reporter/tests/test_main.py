"""Unit tests for Network Interface Reporter."""

import json
import socket
import unittest
from types import SimpleNamespace

from main import (
    collect_network_interfaces,
    format_console_report,
    format_json_report,
    parse_args,
)


class TestNetworkInterfaceReporter(unittest.TestCase):
    """Test suite for Network Interface Reporter."""

    def setUp(self) -> None:
        # Mock address object structure returned by psutil.net_if_addrs()
        self.ipv4_addr = SimpleNamespace(
            family=socket.AF_INET,
            address="192.168.1.50",
            netmask="255.255.255.0",
            broadcast="192.168.1.255",
            ptp=None,
        )
        self.ipv6_addr = SimpleNamespace(
            family=socket.AF_INET6,
            address="fe80::1",
            netmask="ffff:ffff:ffff:ffff::",
            broadcast=None,
            ptp=None,
        )
        self.mac_addr = SimpleNamespace(
            family=getattr(socket, "AF_PACKET", -1),
            address="00:11:22:33:44:55",
            netmask=None,
            broadcast=None,
            ptp=None,
        )

        self.mock_addrs = {
            "eth0": [self.ipv4_addr, self.ipv6_addr, self.mac_addr],
            "lo": [
                SimpleNamespace(
                    family=socket.AF_INET,
                    address="127.0.0.1",
                    netmask="255.0.0.0",
                    broadcast=None,
                    ptp=None,
                )
            ],
        }

        self.mock_stats = {
            "eth0": SimpleNamespace(isup=True, speed=1000, mtu=1500),
            "lo": SimpleNamespace(isup=False, speed=0, mtu=65536),
        }

    def test_collect_network_interfaces(self) -> None:
        interfaces = collect_network_interfaces(
            addrs_data=self.mock_addrs, stats_data=self.mock_stats
        )

        self.assertEqual(len(interfaces), 2)
        eth0 = next(i for i in interfaces if i["name"] == "eth0")
        self.assertEqual(eth0["status"], "UP")
        self.assertTrue(eth0["is_up"])
        self.assertEqual(eth0["mac_address"], "00:11:22:33:44:55")
        self.assertEqual(len(eth0["ipv4"]), 1)
        self.assertEqual(eth0["ipv4"][0]["address"], "192.168.1.50")
        self.assertEqual(len(eth0["ipv6"]), 1)

    def test_format_json_report(self) -> None:
        interfaces = collect_network_interfaces(
            addrs_data=self.mock_addrs, stats_data=self.mock_stats
        )
        json_output = format_json_report(interfaces)
        data = json.loads(json_output)

        self.assertIn("interfaces", data)
        self.assertEqual(len(data["interfaces"]), 2)

    def test_format_console_report(self) -> None:
        interfaces = collect_network_interfaces(
            addrs_data=self.mock_addrs, stats_data=self.mock_stats
        )
        report = format_console_report(interfaces)

        self.assertIn("eth0", report)
        self.assertIn("192.168.1.50", report)
        self.assertIn("00:11:22:33:44:55", report)

    def test_parse_args(self) -> None:
        args = parse_args(["--json", "--active-only"])
        self.assertTrue(args.json)
        self.assertTrue(args.active_only)


if __name__ == "__main__":
    unittest.main()

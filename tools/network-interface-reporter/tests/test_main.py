"""Unit tests for Network Interface Reporter."""

import importlib
import io
import json
import socket
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import patch

import main as main_module
from main import (
    collect_network_interfaces,
    format_console_report,
    format_json_report,
    get_address_family_name,
    main,
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


class TestAddressFamilyNames(unittest.TestCase):
    """Test suite for socket family constant translation."""

    def test_inet_families(self) -> None:
        self.assertEqual(get_address_family_name(socket.AF_INET), "IPv4")
        self.assertEqual(get_address_family_name(socket.AF_INET6), "IPv6")

    def test_mac_and_unknown_families(self) -> None:
        """MAC detection works via psutil, socket constants, or falls back."""
        fake_socket = SimpleNamespace(AF_INET=2, AF_INET6=23, AF_LINK=17, AF_PACKET=999)
        fake_psutil = SimpleNamespace(AF_LINK=17)
        with patch.object(main_module, "socket", fake_socket), patch.object(
            main_module, "psutil", fake_psutil
        ):
            self.assertEqual(get_address_family_name(17), "MAC")
            self.assertEqual(get_address_family_name(999), "MAC")
            # Without any known constant match the numeric family is shown.
            self.assertEqual(get_address_family_name(12345), "12345")


class TestPsutilAbsence(unittest.TestCase):
    """Test suite for behavior when the psutil package is unavailable."""

    def test_import_guard_and_runtime_error(self) -> None:
        """Reloading without psutil keeps collection explicit and safe."""
        with patch.dict(sys.modules, {"psutil": None}):
            reloaded = importlib.reload(main_module)
            with self.assertRaises(RuntimeError):
                reloaded.collect_network_interfaces()
            # With address data supplied, stats default to empty gracefully.
            interfaces = reloaded.collect_network_interfaces(
                addrs_data={"lo0": []}, stats_data=None
            )
            self.assertEqual(interfaces[0]["name"], "lo0")
            self.assertTrue(interfaces[0]["is_up"])
        importlib.reload(main_module)  # restore normal psutil binding

    def test_stats_default_when_psutil_present(self) -> None:
        """Missing stats entries fall back to permissive defaults."""
        with patch.object(
            main_module.psutil,
            "net_if_stats",
            return_value={},
            create=True,
        ):
            interfaces = collect_network_interfaces(addrs_data={"enp3s0": []})
        self.assertEqual(interfaces[0]["status"], "UP")
        self.assertEqual(interfaces[0]["speed_mbps"], 0)
        self.assertEqual(interfaces[0]["mac_address"], "N/A")


class TestReportFormatting(unittest.TestCase):
    """Test suite for report rendering edge cases."""

    def test_empty_report(self) -> None:
        report = format_console_report([])
        self.assertIn("No network interfaces found.", report)

    def test_interface_without_ipv4(self) -> None:
        report = format_console_report(
            [
                {
                    "name": "vpn0",
                    "is_up": True,
                    "status": "UP",
                    "speed_mbps": 0,
                    "mac_address": "N/A",
                    "ipv4": [],
                    "ipv6": [{"address": "fd00::5", "netmask": "ffff::"}],
                }
            ]
        )
        self.assertIn("IPv4 Addresses: None", report)
        self.assertIn("fd00::5", report)


class TestCliEntryPoint(unittest.TestCase):
    """End-to-end tests for main() output modes and error handling."""

    SAMPLE_IFACES: List[Dict[str, Any]] = [
        {
            "name": "eth0",
            "is_up": True,
            "status": "UP",
            "speed_mbps": 1000,
            "mac_address": "00:11:22:33:44:55",
            "ipv4": [
                {
                    "address": "192.168.1.50",
                    "netmask": "255.255.255.0",
                    "broadcast": "192.168.1.255",
                }
            ],
            "ipv6": [],
        },
        {
            "name": "wifi-down",
            "is_up": False,
            "status": "DOWN",
            "speed_mbps": 0,
            "mac_address": "N/A",
            "ipv4": [],
            "ipv6": [],
        },
    ]

    def test_main_console_json_and_active_only(self) -> None:
        with patch.object(main_module, "collect_network_interfaces") as mock_collect:
            mock_collect.return_value = list(self.SAMPLE_IFACES)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["--active-only"])
            self.assertEqual(rc, 0)
            self.assertIn("[UP]", buf.getvalue())
            self.assertNotIn("wifi-down", buf.getvalue())

            buf_json = io.StringIO()
            with redirect_stdout(buf_json):
                rc = main(["--json"])
            self.assertEqual(rc, 0)
            payload: Dict[str, Any] = json.loads(buf_json.getvalue())
            self.assertEqual(len(payload["interfaces"]), 2)

    def test_main_returns_error_without_psutil(self) -> None:
        with patch.object(main_module, "collect_network_interfaces") as mock_c:
            mock_c.side_effect = RuntimeError("psutil package is required")
            buf_err = io.StringIO()
            from contextlib import redirect_stderr

            with redirect_stderr(buf_err):
                rc = main([])
            self.assertEqual(rc, 1)
            self.assertIn("Error inspecting network interfaces", buf_err.getvalue())


if __name__ == "__main__":
    unittest.main()

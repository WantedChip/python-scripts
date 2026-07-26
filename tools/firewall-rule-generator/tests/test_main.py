"""Unit tests for Firewall Rule Generator."""

import tempfile
import unittest
from pathlib import Path

from main import FirewallRule, generate_iptables, generate_ufw, load_rules, parse_args


class TestFirewallRuleGenerator(unittest.TestCase):
    """Test suite for Firewall Rule Generator."""

    def test_rule_validation(self) -> None:
        rule_valid = FirewallRule(
            action="allow",
            direction="in",
            protocol="tcp",
            port=80,
            source="192.168.1.0/24",
        )
        rule_valid.validate()

        rule_invalid_action = FirewallRule(action="invalid_action")
        with self.assertRaises(ValueError):
            rule_invalid_action.validate()

        rule_invalid_ip = FirewallRule(action="allow", source="999.999.999.999")
        with self.assertRaises(ValueError):
            rule_invalid_ip.validate()

    def test_generate_iptables(self) -> None:
        rule = FirewallRule(
            action="allow",
            direction="in",
            protocol="tcp",
            port=443,
            source="10.0.0.0/8",
            comment="Allow HTTPS",
        )
        script = generate_iptables([rule])
        expected_line = "iptables -A INPUT -p tcp -s 10.0.0.0/8 --dport 443 -j ACCEPT"
        self.assertIn(expected_line, script)
        self.assertIn("# Allow HTTPS", script)

    def test_generate_ufw(self) -> None:
        rule = FirewallRule(
            action="deny",
            direction="in",
            protocol="tcp",
            port=22,
            source="any",
            comment="Block SSH",
        )
        script = generate_ufw([rule])
        self.assertIn("ufw deny in port 22/tcp", script)

    def test_load_json_rules(self) -> None:
        json_content = """{
            "rules": [
                {
                    "action": "allow",
                    "direction": "in",
                    "protocol": "tcp",
                    "port": 80
                }
            ]
        }"""
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:
            f.write(json_content)
            temp_path = Path(f.name)

        try:
            rules = load_rules(temp_path)
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0].action, "allow")
            self.assertEqual(rules[0].port, "80")
        finally:
            temp_path.unlink()

    def test_parse_args(self) -> None:
        args = parse_args(["rules.json", "--target", "ufw", "-o", "out.sh"])
        self.assertEqual(args.input_file, "rules.json")
        self.assertEqual(args.target, "ufw")
        self.assertEqual(args.output, "out.sh")


if __name__ == "__main__":
    unittest.main()

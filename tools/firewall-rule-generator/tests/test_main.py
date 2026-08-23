"""Unit tests for Firewall Rule Generator."""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import main as fw
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


class TestRuleValidation(unittest.TestCase):
    """Validation branches for directions, protocols, and endpoints."""

    def test_invalid_direction_raises(self) -> None:
        """An unknown direction is rejected with ValueError."""
        with self.assertRaises(ValueError):
            FirewallRule(action="allow", direction="sideways").validate()

    def test_invalid_protocol_raises(self) -> None:
        """An unknown protocol is rejected with ValueError."""
        with self.assertRaises(ValueError):
            FirewallRule(action="allow", protocol="gre").validate()

    def test_invalid_destination_cidr_raises(self) -> None:
        """A malformed destination address is rejected with ValueError."""
        with self.assertRaises(ValueError):
            FirewallRule(action="allow", destination="10.0.0.256").validate()

    def test_action_and_attributes_are_normalized(self) -> None:
        """Actions, directions, and protocols are lowercased; port stringified."""
        rule = FirewallRule(action="ALLOW", direction="IN", protocol="TCP", port=8080)
        self.assertEqual(rule.action, "allow")
        self.assertEqual(rule.direction, "in")
        self.assertEqual(rule.protocol, "tcp")
        self.assertEqual(rule.port, "8080")


class TestLoadRules(unittest.TestCase):
    """Spec-file loading: formats, fallbacks, and error reporting."""

    def _write_spec(self, name: str, content: str) -> Path:
        """Write a rules spec into a temp file and return its path."""
        tmp = tempfile.NamedTemporaryFile("w+", suffix=name, delete=False)
        tmp.write(content)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return Path(tmp.name)

    def test_missing_spec_file_raises_file_not_found(self) -> None:
        """A nonexistent spec path raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_rules(Path("Z:/definitely/missing.json"))

    def test_yaml_spec_is_parsed_when_pyyaml_available(self) -> None:
        """YAML specs load through PyYAML when installed."""
        spec = self._write_spec(
            ".yaml",
            "rules:\n  - action: deny\n    protocol: udp\n    port: 53\n",
        )
        rules = load_rules(spec)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].action, "deny")
        self.assertEqual(rules[0].port, "53")

    def test_yaml_without_pyyaml_raises_runtime_error(self) -> None:
        """YAML specs raise RuntimeError when PyYAML is unavailable."""
        spec = self._write_spec(".yaml", "rules: []\n")
        with patch.object(fw, "HAS_YAML", False), self.assertRaises(RuntimeError):
            load_rules(spec)

    def test_invalid_json_without_yaml_raises_value_error(self) -> None:
        """Unparseable JSON without PyYAML raises a descriptive ValueError."""
        spec = self._write_spec(".json", "{ definitely not json")
        with patch.object(fw, "HAS_YAML", False), self.assertRaises(ValueError):
            load_rules(spec)

    def test_malformed_json_falls_back_to_yaml(self) -> None:
        """JSON files that fail to parse fall back to the YAML parser."""
        yaml_content = "rules:\n  - action: allow\n    protocol: icmp\n"
        spec = self._write_spec(".json", yaml_content)
        rules = load_rules(spec)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].protocol, "icmp")

    def test_non_mapping_root_raises_value_error(self) -> None:
        """A scalar YAML document produces a clean ValueError."""
        spec = self._write_spec(".yaml", "just a plain string\n")
        with self.assertRaises(ValueError):
            load_rules(spec)

    def test_rules_key_not_a_list_raises_value_error(self) -> None:
        """A non-list 'rules' key raises ValueError."""
        spec = self._write_spec(".json", '{"rules": {"a": 1}}')
        with self.assertRaises(ValueError):
            load_rules(spec)

    def test_invalid_rule_reports_its_index(self) -> None:
        """The first invalid rule is reported as rule #1."""
        spec = self._write_spec(".json", '{"rules": [{"action": "bogus"}]}')
        with self.assertRaises(ValueError) as ctx:
            load_rules(spec)
        self.assertIn("Error in rule #1", str(ctx.exception))


class TestScriptGeneration(unittest.TestCase):
    """iptables / ufw command mapping for actions, chains, and endpoints."""

    def test_iptables_drop_reject_and_output_chain(self) -> None:
        """deny maps to DROP, reject to REJECT, egress to OUTPUT chain."""
        drop_rule = FirewallRule(action="deny", destination="10.0.0.1")
        reject_rule = FirewallRule(action="reject", direction="egress")
        script = generate_iptables([drop_rule, reject_rule])

        self.assertIn("iptables -A INPUT -d 10.0.0.1 -j DROP", script)
        self.assertIn("iptables -A OUTPUT -j REJECT", script)
        self.assertIn("iptables -F", script)

    def test_iptables_accept_alias_and_any_protocol(self) -> None:
        """'accept' maps to ACCEPT and 'any' omits the -p flag."""
        rule = FirewallRule(action="accept")
        script = generate_iptables([rule])
        self.assertIn("iptables -A INPUT -j ACCEPT", script)

    def test_ufw_from_to_and_protocol_only(self) -> None:
        """ufw output includes from/to clauses and proto-only port suffix."""
        allow_rule = FirewallRule(
            action="allow",
            source="10.0.0.0/8",
            destination="192.168.1.0/24",
            protocol="tcp",
        )
        plain_rule = FirewallRule(action="deny", protocol="any")
        script = generate_ufw([allow_rule, plain_rule])

        self.assertIn("ufw allow in from 10.0.0.0/8 to 192.168.1.0/24 port tcp", script)
        self.assertIn("ufw deny in\n", script)


class TestMainCli(unittest.TestCase):
    """End-to-end CLI runs against temporary spec files."""

    def setUp(self) -> None:
        self.work_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.work_dir, True)

    def _write_spec(self, name: str, content: str) -> Path:
        """Write a rules spec into the temp work dir and return its path."""
        spec = Path(self.work_dir) / f"spec{name}"
        spec.write_text(content, encoding="utf-8")
        return spec

    def test_main_prints_script_to_stdout(self) -> None:
        """Without --output the generated script goes to stdout; exit 0."""
        spec = self._write_spec(".json", '{"rules": [{"action": "allow"}]}')
        out_buf = io.StringIO()

        with redirect_stdout(out_buf):
            code = fw.main([str(spec)])

        self.assertEqual(code, 0)
        self.assertIn("iptables -A INPUT -j ACCEPT", out_buf.getvalue())

    def test_main_writes_output_file_for_ufw_target(self) -> None:
        """--output plus --target ufw writes the ufw script to disk."""
        spec = self._write_spec(".json", '{"rules": [{"action": "deny"}]}')
        out_path = Path(self.work_dir) / "fw.sh"

        out_buf = io.StringIO()
        with redirect_stdout(out_buf):
            code = fw.main([str(spec), "--target", "ufw", "--output", str(out_path)])

        self.assertEqual(code, 0)
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("ufw --force reset", content)
        self.assertIn("ufw deny in", content)
        self.assertIn("Successfully generated ufw script", out_buf.getvalue())

    def test_main_missing_input_returns_one(self) -> None:
        """A missing input file makes the CLI exit 1 with an error message."""
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            code = fw.main([str(Path(self.work_dir) / "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("Error loading firewall rules", err_buf.getvalue())

    def test_main_invalid_spec_returns_one(self) -> None:
        """An invalid rule inside the spec makes the CLI exit 1."""
        spec = self._write_spec(".json", '{"rules": [{"action": "?!"}]}')
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            code = fw.main([str(spec)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

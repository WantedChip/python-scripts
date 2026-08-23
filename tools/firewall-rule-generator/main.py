"""Firewall Rule Generator.

Generates iptables or ufw shell scripts from YAML or JSON rule specifications.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import ipaddress
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class FirewallRule:
    """Dataclass representing a normalized firewall rule."""

    def __init__(
        self,
        action: str,
        direction: str = "in",
        protocol: str = "any",
        port: Optional[Any] = None,
        source: str = "any",
        destination: str = "any",
        comment: Optional[str] = None,
    ) -> None:
        self.action: str = action.lower()
        self.direction: str = direction.lower()
        self.protocol: str = protocol.lower()
        self.port: Optional[str] = str(port) if port is not None else None
        self.source: str = source
        self.destination: str = destination
        self.comment: Optional[str] = comment

    def validate(self) -> None:
        """Validates rule attributes. Raises ValueError if invalid."""
        valid_actions = {"allow", "deny", "accept", "drop", "reject"}
        if self.action not in valid_actions:
            msg = f"Invalid action '{self.action}'. Must be one of {valid_actions}"
            raise ValueError(msg)

        valid_directions = {"in", "out", "input", "output", "ingress", "egress"}
        if self.direction not in valid_directions:
            msg = (
                f"Invalid direction '{self.direction}'. Must be one of "
                f"{valid_directions}"
            )
            raise ValueError(msg)

        valid_protocols = {"tcp", "udp", "icmp", "any", "all"}
        if self.protocol not in valid_protocols:
            msg = (
                f"Invalid protocol '{self.protocol}'. Must be one of "
                f"{valid_protocols}"
            )
            raise ValueError(msg)

        if self.source.lower() != "any":
            self._validate_ip_or_cidr(self.source)

        if self.destination.lower() != "any":
            self._validate_ip_or_cidr(self.destination)

    @staticmethod
    def _validate_ip_or_cidr(val: str) -> None:
        try:
            ipaddress.ip_network(val, strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid IP address or CIDR range: '{val}'") from exc


def load_rules(file_path: Path) -> List[FirewallRule]:
    """Loads and validates firewall rules from a JSON or YAML file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: '{file_path}'")

    content = file_path.read_text(encoding="utf-8")
    data: Dict[str, Any] = {}

    if file_path.suffix in [".yaml", ".yml"]:
        if not HAS_YAML:
            msg = "PyYAML package is required to parse YAML files."
            raise RuntimeError(msg)
        data = yaml.safe_load(content) or {}
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as err:
            if HAS_YAML:
                # Fallback attempt with YAML parser
                data = yaml.safe_load(content) or {}
            else:
                msg = f"Failed to parse JSON file '{file_path}': {err}"
                raise ValueError(msg) from err

    raw_rules = data.get("rules", []) if isinstance(data, dict) else None
    if not isinstance(raw_rules, list):
        raise ValueError("Rules specification must be a mapping with a 'rules' list.")

    rules: List[FirewallRule] = []
    for idx, item in enumerate(raw_rules):
        rule = FirewallRule(
            action=item.get("action", "allow"),
            direction=item.get("direction", "in"),
            protocol=item.get("protocol", "any"),
            port=item.get("port"),
            source=item.get("source", "any"),
            destination=item.get("destination", "any"),
            comment=item.get("comment"),
        )
        try:
            rule.validate()
        except ValueError as err:
            raise ValueError(f"Error in rule #{idx + 1}: {err}") from err
        rules.append(rule)

    return rules


def generate_iptables(rules: List[FirewallRule]) -> str:
    """Generates iptables shell script commands from a list of rules."""
    lines: List[str] = [
        "#!/usr/bin/env bash",
        "# Generated iptables Firewall Rules Script",
        "set -euo pipefail",
        "",
        "# Flush existing rules",
        "iptables -F",
        "iptables -X",
        "",
    ]

    for rule in rules:
        if rule.comment:
            lines.append(f"# {rule.comment}")

        # Map action
        target = "ACCEPT"
        if rule.action in ["deny", "drop"]:
            target = "DROP"
        elif rule.action == "reject":
            target = "REJECT"

        # Map chain
        chain = "INPUT"
        if rule.direction in ["out", "output", "egress"]:
            chain = "OUTPUT"

        cmd_parts = ["iptables", "-A", chain]

        if rule.protocol not in ("any", "all"):
            cmd_parts.extend(["-p", rule.protocol])

        if rule.source.lower() != "any":
            cmd_parts.extend(["-s", rule.source])

        if rule.destination.lower() != "any":
            cmd_parts.extend(["-d", rule.destination])

        if rule.port and rule.protocol in ["tcp", "udp"]:
            cmd_parts.extend(["--dport", str(rule.port)])

        cmd_parts.extend(["-j", target])
        lines.append(" ".join(cmd_parts))

    lines.append("")
    return "\n".join(lines)


def generate_ufw(rules: List[FirewallRule]) -> str:
    """Generates ufw shell script commands from a list of rules."""
    lines: List[str] = [
        "#!/usr/bin/env bash",
        "# Generated UFW Firewall Rules Script",
        "set -euo pipefail",
        "",
        "# Reset UFW to default state",
        "ufw --force reset",
        "ufw default deny incoming",
        "ufw default allow outgoing",
        "",
    ]

    for rule in rules:
        if rule.comment:
            lines.append(f"# {rule.comment}")

        ufw_action = "allow" if rule.action in ["allow", "accept"] else "deny"
        direction = "in" if rule.direction in ["in", "input", "ingress"] else "out"

        cmd_parts = ["ufw", ufw_action, direction]

        if rule.source.lower() != "any":
            cmd_parts.extend(["from", rule.source])

        if rule.destination.lower() != "any":
            cmd_parts.extend(["to", rule.destination])

        if rule.port or rule.protocol not in ("any", "all"):
            port_proto = ""
            if rule.port:
                port_proto = str(rule.port)
            if rule.protocol in ["tcp", "udp"]:
                port_proto += f"/{rule.protocol}" if port_proto else rule.protocol
            if port_proto:
                cmd_parts.extend(["port", port_proto])

        lines.append(" ".join(cmd_parts))

    lines.append("\nufw --force enable")
    lines.append("")
    return "\n".join(lines)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Firewall Rule Generator")
    parser.add_argument(
        "input_file",
        type=str,
        help="Path to rules spec file (JSON or YAML)",
    )
    parser.add_argument(
        "--target",
        "-t",
        choices=["iptables", "ufw"],
        default="iptables",
        help="Target firewall tool (default: iptables)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output script file path (default: stdout)",
    )
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parsed = parse_args(args)

    input_path = Path(parsed.input_file)
    try:
        rules = load_rules(input_path)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
        print(f"Error loading firewall rules: {e}", file=sys.stderr)
        return 1

    if parsed.target == "ufw":
        script_content = generate_ufw(rules)
    else:
        script_content = generate_iptables(rules)

    if parsed.output:
        out_path = Path(parsed.output)
        out_path.write_text(script_content, encoding="utf-8")
        print(f"Successfully generated {parsed.target} script at '{out_path}'")
    else:
        print(script_content)

    return 0


if __name__ == "__main__":
    sys.exit(main())

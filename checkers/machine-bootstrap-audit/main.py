"""Machine Bootstrap Audit Tool.

Inspects setup/bootstrap scripts (shell & Python) statically and dynamically
to report hidden environment assumptions such as interactive prompts, un-checked
required binaries, privilege escalations (sudo), and hardcoded user paths.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-few-public-methods

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class AuditFinding:
    """Class representing an identified assumption or issue in a setup script."""

    line_number: int
    category: str
    severity: str
    description: str
    code_line: str


INTERACTIVE_PATTERNS = [
    (
        re.compile(r"\bread\b|\bread\s+-p\b", re.IGNORECASE),
        "Shell interactive 'read' prompt",
    ),
    (
        re.compile(r"\binput\s*\(", re.IGNORECASE),
        "Python interactive 'input()' prompt",
    ),
    (re.compile(r"\bsys\.stdin\b", re.IGNORECASE), "Direct read from stdin"),
]

PRIVILEGE_PATTERNS = [
    (
        re.compile(r"\bsudo\b", re.IGNORECASE),
        "Explicit 'sudo' privilege escalation call",
    ),
    (re.compile(r"\bsu\s+", re.IGNORECASE), "User switching 'su' command"),
    (re.compile(r"\brunas\b", re.IGNORECASE), "Windows 'runas' command"),
]

HARDCODED_PATH_PATTERNS = [
    (
        re.compile(r"/home/\w+", re.IGNORECASE),
        "Hardcoded user home path (/home/user)",
    ),
    (
        re.compile(r"C:\\Users\\\w+", re.IGNORECASE),
        "Hardcoded Windows user profile path",
    ),
    (
        re.compile(r"/usr/local/bin", re.IGNORECASE),
        "Hardcoded system binary path (/usr/local/bin)",
    ),
    (re.compile(r"/opt/\w+", re.IGNORECASE), "Hardcoded /opt path"),
]

BINARY_REGEX = (
    r"\b(docker|kubectl|npm|yarn|cargo|pip|brew|apt|apt-get|yum|pacman|terraform)\b"
)
UNCHECKED_BINARY_PATTERNS = [
    (
        re.compile(BINARY_REGEX, re.IGNORECASE),
        "Direct invocation of external tool without pre-flight existence check",
    ),
]

# Matches existence checks such as `command -v docker`, `which terraform`,
# `type npm`, or Python's `shutil.which("docker")` so later references to the
# same binary are treated as verified (pre-flight check already present).
BINARY_CHECK_PATTERN = re.compile(
    r"\b(?:command\s+-v|which|type)\s+([A-Za-z_][A-Za-z0-9_.-]*)"
    r"|shutil\.which\(\s*[\"']([A-Za-z_][A-Za-z0-9_.-]*)[\"']",
    re.IGNORECASE,
)


def audit_script_file(script_path: Path) -> List[AuditFinding]:
    """Perform static analysis on a setup script file."""
    findings: List[AuditFinding] = []
    if not script_path.exists():
        return [
            AuditFinding(
                line_number=0,
                category="File Missing",
                severity="ERROR",
                description=f"Script file not found: {script_path}",
                code_line="",
            )
        ]

    content = script_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    checked_binaries: Set[str] = set()

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        for check_match in BINARY_CHECK_PATTERN.finditer(line):
            verified = check_match.group(1) or check_match.group(2)
            checked_binaries.add(verified.lower())

        for pattern, desc in INTERACTIVE_PATTERNS:
            if pattern.search(line):
                findings.append(
                    AuditFinding(
                        line_number=idx,
                        category="Interactive Prompt",
                        severity="WARNING",
                        description=desc,
                        code_line=stripped,
                    )
                )

        for pattern, desc in PRIVILEGE_PATTERNS:
            if pattern.search(line):
                findings.append(
                    AuditFinding(
                        line_number=idx,
                        category="Privilege Escalation",
                        severity="WARNING",
                        description=desc,
                        code_line=stripped,
                    )
                )

        for pattern, desc in HARDCODED_PATH_PATTERNS:
            if pattern.search(line):
                findings.append(
                    AuditFinding(
                        line_number=idx,
                        category="Hardcoded Path",
                        severity="WARNING",
                        description=desc,
                        code_line=stripped,
                    )
                )

        if not any(
            chk in line for chk in ["command -v", "which ", "type ", "shutil.which"]
        ):
            for pattern, desc in UNCHECKED_BINARY_PATTERNS:
                for bin_match in pattern.finditer(line):
                    if bin_match.group(0).lower() in checked_binaries:
                        continue
                    findings.append(
                        AuditFinding(
                            line_number=idx,
                            category="Unchecked Binary Dependency",
                            severity="INFO",
                            description=desc,
                            code_line=stripped,
                        )
                    )

    return findings


def generate_audit_report(script_path: Path, findings: List[AuditFinding]) -> str:
    """Format audit findings into a clean report."""
    output = []
    output.append("=== MACHINE BOOTSTRAP AUDIT REPORT ===")
    output.append(f"Target Script: {script_path}")
    output.append(f"Total Findings Identified: {len(findings)}\n")

    if not findings:
        output.append("SUCCESS: No hidden assumptions or risky patterns detected.")
        return "\n".join(output)

    by_category: dict[str, List[AuditFinding]] = {}
    for f in findings:
        by_category.setdefault(f.category, []).append(f)

    for category, items in sorted(by_category.items()):
        output.append(f"[{category}] ({len(items)} occurrence(s)):")
        for item in items:
            output.append(
                f"  - Line {item.line_number} [{item.severity}]: {item.description}"
            )
            output.append(f"    Code: {item.code_line}")
        output.append("")

    return "\n".join(output)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = "Audit setup and machine bootstrap scripts for hidden assumptions."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "scripts",
        nargs="+",
        help="Paths to setup/bootstrap scripts (.sh, .bash, .py, .ps1).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail (exit non-zero) if any WARNING or ERROR findings are detected.",
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for machine-bootstrap-audit."""
    parsed = parse_args(args)

    total_warnings = 0
    total_errors = 0

    for s_path in parsed.scripts:
        path = Path(s_path)
        findings = audit_script_file(path)
        report = generate_audit_report(path, findings)
        print(report)

        for f in findings:
            if f.severity == "WARNING":
                total_warnings += 1
            elif f.severity == "ERROR":
                total_errors += 1

    if parsed.strict and (total_warnings > 0 or total_errors > 0):
        print(f"\nAUDIT FAILED: {total_errors} Error(s), {total_warnings} Warning(s).")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

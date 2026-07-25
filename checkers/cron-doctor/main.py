#!/usr/bin/env python3
"""Cron Doctor Utility.

Audits cron entries and scheduled task files for syntax, missing executables,
stale paths, permission issues, missing error redirects, and overlapping executions.
"""

# pylint: disable=too-many-branches,too-many-locals

import argparse
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class Issue:
    """Represents an issue found during cron auditing."""

    severity: str  # 'ERROR', 'WARNING', 'INFO'
    line_num: int
    raw_entry: str
    issue_type: str
    message: str


class CronDoctor:
    """Parses and audits cron schedule files or strings."""

    CRON_EXPRESSION_REGEX = re.compile(
        r"^\s*(@(?:reboot|yearly|annually|monthly|weekly|daily|midnight|hourly)|"
        r"(?:[^\s]+\s+){4}[^\s]+)\s+(.+)$"
    )

    def __init__(self, custom_path: Optional[str] = None):
        self.system_path = custom_path or os.environ.get("PATH", "")

    def _parse_line(self, line: str) -> Optional[Tuple[str, str]]:
        """Extract schedule expression and command string from cron line."""
        line = line.strip()
        if not line or line.startswith("#") or "=" in line.split()[0]:
            return None

        match = self.CRON_EXPRESSION_REGEX.match(line)
        if match:
            return match.group(1), match.group(2)
        return None

    def _extract_command_binary(self, command: str) -> Tuple[str, List[str]]:
        """Extract main executable command and command arguments."""
        # Simple extraction handling quotes or plain tokens
        tokens = command.split()
        if not tokens:
            return "", []

        # Ignore env prefixes like VAR=val
        idx = 0
        while idx < len(tokens) and "=" in tokens[idx]:
            idx += 1
        if idx < len(tokens):
            return tokens[idx], tokens[idx + 1 :]  # noqa: E203
        return "", []

    def audit_entry(self, line_num: int, raw_line: str) -> List[Issue]:
        """Audit a single cron line entry."""
        issues: List[Issue] = []
        parsed = self._parse_line(raw_line)

        if not parsed:
            return issues

        schedule, full_cmd = parsed

        # 1. Overlap Check (Frequent schedule without lockfile)
        freq_schedules = ("* * * * *", "*/1 * * * *", "@hourly")
        lock_tools = ("flock", "lockfile", "mkdir")
        if schedule in freq_schedules and not any(t in full_cmd for t in lock_tools):
            issues.append(
                Issue(
                    severity="WARNING",
                    line_num=line_num,
                    raw_entry=raw_line,
                    issue_type="POSSIBLE_OVERLAP",
                    message=(
                        "High-frequency execution schedule without process lock "
                        "mechanism (e.g. flock)."
                    ),
                )
            )

        # 2. Check stderr redirection / silent failure risks
        has_stderr = "2>" in full_cmd or "2>&1" in full_cmd or "&>" in full_cmd
        if not has_stderr:
            issues.append(
                Issue(
                    severity="WARNING",
                    line_num=line_num,
                    raw_entry=raw_line,
                    issue_type="SILENT_FAILURE_RISK",
                    message=(
                        "Command lacks explicit stderr output redirection "
                        "(2>&1 or 2>file)."
                    ),
                )
            )

        # 3. Executable existence check
        binary_cmd, args = self._extract_command_binary(full_cmd)
        if binary_cmd:
            bin_path = Path(binary_cmd)
            is_abs = (
                binary_cmd.startswith("/")
                or binary_cmd.startswith("\\")
                or bin_path.is_absolute()
            )
            if is_abs:
                if not bin_path.exists():
                    issues.append(
                        Issue(
                            severity="ERROR",
                            line_num=line_num,
                            raw_entry=raw_line,
                            issue_type="MISSING_EXECUTABLE",
                            message=f"Executable path '{binary_cmd}' does not exist.",
                        )
                    )
                elif not os.access(bin_path, os.X_OK):
                    issues.append(
                        Issue(
                            severity="ERROR",
                            line_num=line_num,
                            raw_entry=raw_line,
                            issue_type="PERMISSION_DENIED",
                            message=(
                                f"Executable path '{binary_cmd}' lacks execute "
                                "permission (+x)."
                            ),
                        )
                    )
            else:
                found = shutil.which(binary_cmd, path=self.system_path)
                if not found:
                    issues.append(
                        Issue(
                            severity="ERROR",
                            line_num=line_num,
                            raw_entry=raw_line,
                            issue_type="COMMAND_NOT_FOUND",
                            message=f"Command '{binary_cmd}' not found on system PATH.",
                        )
                    )

        # 4. Check script arguments if pointing to a local file
        script_exts = (".py", ".sh", ".bash", ".pl", ".rb")
        for arg in args:
            if arg.startswith("/") or arg.startswith("./"):
                arg_path = Path(arg.split(">")[0].strip())
                if arg_path.suffix in script_exts and not arg_path.exists():
                    issues.append(
                        Issue(
                            severity="ERROR",
                            line_num=line_num,
                            raw_entry=raw_line,
                            issue_type="STALE_SCRIPT_PATH",
                            message=f"Target script file '{arg_path}' does not exist.",
                        )
                    )

        return issues

    def audit_file(self, file_path: Path) -> List[Issue]:
        """Audit an entire crontab or cron format file."""
        if not file_path.exists():
            raise FileNotFoundError(f"File '{file_path}' does not exist.")

        all_issues = []
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f, 1):
                issues = self.audit_entry(idx, line)
                all_issues.extend(issues)
        return all_issues


def main() -> None:
    """Main CLI entrypoint for Cron Doctor."""
    parser = argparse.ArgumentParser(
        description="Audit crontabs and scheduled task entries for errors."
    )
    parser.add_argument("-f", "--file", type=Path, help="Path to crontab file to audit")
    parser.add_argument(
        "-e", "--entry", type=str, help="Single cron line entry string to audit"
    )
    args = parser.parse_args()

    doctor = CronDoctor()
    issues: List[Issue] = []

    if args.entry:
        issues = doctor.audit_entry(1, args.entry)
    elif args.file:
        issues = doctor.audit_file(args.file)
    else:
        parser.error("Please specify either --file or --entry.")

    print("=== Cron Doctor Health Report ===")
    if not issues:
        print("HEALTHY: No issues or warnings found in cron configuration.")
    else:
        for issue in issues:
            print(f"[{issue.severity}] Line {issue.line_num}: {issue.issue_type}")
            print(f"   Entry:   {issue.raw_entry.strip()}")
            print(f"   Details: {issue.message}\n")


if __name__ == "__main__":
    main()

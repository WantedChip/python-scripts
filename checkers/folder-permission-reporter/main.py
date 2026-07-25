"""Folder Permission Reporter Tool.

Audits directory permissions and reports files/folders with overly permissive bit
modes (world-writable, executable data files, missing sticky bits) across Unix
and Windows systems.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-few-public-methods

import argparse
import json
import pathlib
import stat
import sys
from dataclasses import asdict, dataclass
from typing import List, Optional

# Non-binary text/data extensions that should typically not be executable
DATA_FILE_EXTENSIONS = {
    ".txt",
    ".json",
    ".csv",
    ".xml",
    ".yaml",
    ".yml",
    ".md",
    ".log",
    ".conf",
    ".ini",
    ".sql",
}


@dataclass
class PermissionIssue:
    """Represents a discovered permission vulnerability or anomaly."""

    path: str
    is_directory: bool
    mode_octal: str
    risk_level: str  # HIGH, MEDIUM, LOW
    reasons: List[str]
    recommended_fix: str


class PermissionAuditor:
    """Audits directory and file permission mode bits."""

    def __init__(self, target_dir: pathlib.Path):
        """Initialize auditor.

        Args:
            target_dir: Directory path to audit.
        """
        self.target_dir = target_dir
        self.issues: List[PermissionIssue] = []

    @staticmethod
    def evaluate_path_permissions(path: pathlib.Path) -> Optional[PermissionIssue]:
        """Inspect single path stat mode and classify security risk level.

        Args:
            path: Target file or directory path.

        Returns:
            PermissionIssue object if risk detected, None if permissions are clean.
        """
        try:
            st = path.stat()
        except OSError:
            return None

        mode = st.st_mode
        mode_octal = oct(stat.S_IMODE(mode))
        is_dir = path.is_dir()
        reasons = []
        risk_level = "LOW"
        recommended_cmds = []

        # Check 1: World-writable (o+w)
        if mode & stat.S_IWOTH:
            reasons.append("World-writable (o+w)")
            risk_level = "HIGH"
            recommended_cmds.append(f"chmod o-w '{path}'")

        # Check 2: Sticky bit missing on world-writable directory
        if is_dir and (mode & stat.S_IWOTH) and not mode & stat.S_ISVTX:
            reasons.append("World-writable directory missing sticky bit (+t)")
            risk_level = "HIGH"
            recommended_cmds.append(f"chmod +t '{path}'")

        # Check 3: SUID or SGID bits set on file
        if not is_dir and (mode & (stat.S_ISUID | stat.S_ISGID)):
            suid_sgid_type = []
            if mode & stat.S_ISUID:
                suid_sgid_type.append("SUID")
            if mode & stat.S_ISGID:
                suid_sgid_type.append("SGID")
            types_str = ", ".join(suid_sgid_type)
            reasons.append(f"Special permission bit set ({types_str})")
            risk_level = "HIGH"
            recommended_cmds.append(f"chmod u-s,g-s '{path}'")

        # Check 4: Executable data file (.txt, .json, .csv, etc.)
        if not is_dir and path.suffix.lower() in DATA_FILE_EXTENSIONS:
            if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                reasons.append(f"Data file with executable bit set ({path.suffix})")
                if risk_level != "HIGH":
                    risk_level = "MEDIUM"
                recommended_cmds.append(f"chmod -x '{path}'")

        # Check 5: Group-writable (g+w)
        if (mode & stat.S_IWGRP) and not mode & stat.S_IWOTH:
            if is_dir or not mode & stat.S_IXGRP:
                reasons.append("Group-writable (g+w)")
                if risk_level not in ("HIGH", "MEDIUM"):
                    risk_level = "LOW"
                recommended_cmds.append(f"chmod g-w '{path}'")

        if not reasons:
            return None

        # Build recommended fix command
        fix_cmd = " && ".join(recommended_cmds)
        if is_dir and "chmod o-w" in fix_cmd:
            fix_cmd = f"chmod 755 '{path}'"
        elif not is_dir and "chmod -x" in fix_cmd and "chmod o-w" in fix_cmd:
            fix_cmd = f"chmod 644 '{path}'"

        return PermissionIssue(
            path=str(path),
            is_directory=is_dir,
            mode_octal=mode_octal,
            risk_level=risk_level,
            reasons=reasons,
            recommended_fix=fix_cmd,
        )

    def run_audit(self) -> List[PermissionIssue]:
        """Perform recursive directory permission audit.

        Returns:
            List of detected PermissionIssue instances.
        """
        self.issues.clear()

        # Audit root target directory
        root_issue = self.evaluate_path_permissions(self.target_dir)
        if root_issue:
            self.issues.append(root_issue)

        # Audit recursive children
        for item in self.target_dir.rglob("*"):
            issue = self.evaluate_path_permissions(item)
            if issue:
                self.issues.append(issue)

        return self.issues


def print_cli_report(issues: List[PermissionIssue], target_dir: pathlib.Path) -> None:
    """Print formatted permission audit report to CLI."""
    print("=" * 85)
    print(f"FOLDER PERMISSION AUDIT REPORT: {target_dir}")
    print("=" * 85)

    high_count = sum(1 for i in issues if i.risk_level == "HIGH")
    med_count = sum(1 for i in issues if i.risk_level == "MEDIUM")
    low_count = sum(1 for i in issues if i.risk_level == "LOW")

    counts_str = (
        f"Total Issues: {len(issues)} | HIGH: {high_count} | "
        f"MEDIUM: {med_count} | LOW: {low_count}"
    )
    print(counts_str)
    print("-" * 85)

    if not issues:
        print("No permission vulnerabilities or anomalies detected.")
        print("=" * 85)
        return

    header_cols = f"{'Risk':<8} | {'Mode':<7} | {'Path':<35} | Issues & Recommendations"
    print(header_cols)
    print("-" * 85)

    for issue in issues:
        path_display = issue.path
        if len(path_display) > 35:
            path_display = "..." + path_display[-32:]

        reasons_str = "; ".join(issue.reasons)
        row_str = (
            f"{issue.risk_level:<8} | {issue.mode_octal:<7} | "
            f"{path_display:<35} | {reasons_str}"
        )
        print(row_str)
        print(f"         | Fix Recommendation: {issue.recommended_fix}")
        print("-" * 85)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Audit directory permissions and report permissive files/folders."
    )
    parser.add_argument("path", type=pathlib.Path, help="Directory path to audit")
    parser.add_argument(
        "--json-output", type=pathlib.Path, help="Path to write JSON format report"
    )
    parser.add_argument(
        "--min-risk",
        choices=["HIGH", "MEDIUM", "LOW"],
        default="LOW",
        help="Minimum risk level filter (default: LOW)",
    )
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parsed = parse_args(args)

    if not parsed.path.exists():
        print(f"Error: Path does not exist: {parsed.path}", file=sys.stderr)
        return 1

    auditor = PermissionAuditor(parsed.path)
    issues = auditor.run_audit()

    # Filter by min-risk if requested
    risk_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    min_rank = risk_rank[parsed.min_risk]
    filtered_issues = [i for i in issues if risk_rank[i.risk_level] >= min_rank]

    print_cli_report(filtered_issues, parsed.path)

    if parsed.json_output:
        try:
            with open(parsed.json_output, "w", encoding="utf-8") as f:
                json.dump([asdict(i) for i in filtered_issues], f, indent=2)
            print(f"JSON audit report written to: {parsed.json_output}")
        except OSError as e:
            print(f"Failed to write JSON report: {e}", file=sys.stderr)

    return 0 if not filtered_issues else 1


if __name__ == "__main__":
    sys.exit(main())

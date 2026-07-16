#!/usr/bin/env python3
# pylint: disable=duplicate-code
"""Test Gap Checker — Compare changed lines of code with test coverage data.

Parses git diff changes and maps them against .coverage data to identify
important code modifications that are untested.
"""

import argparse
import os
import re
import subprocess  # nosec B404 - used to run git to retrieve repository diff
import sys
from typing import Any, Dict, List, Optional, Set

import coverage


def get_repo_root() -> str:
    """Get the absolute path to the git repository root.

    Returns:
        The repository root directory path.
    """
    try:
        # Run git command to get the top-level directory.
        # No shell=True; command is simple list with git binary.
        res = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return os.getcwd()


def get_git_diff(ref: Optional[str] = None) -> str:
    """Retrieve git diff output from the repository.

    Args:
        ref: Optional commit ref or branch to diff against (e.g. 'origin/main').

    Returns:
        The raw diff text.
    """
    cmd = ["git", "diff", "-U0"]
    if ref:
        cmd.append(ref)

    try:
        # No shell=True; cmd is a list, input is git commands
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )  # nosec B603
        return res.stdout
    except (subprocess.SubprocessError, FileNotFoundError) as err:
        print(f"Warning: Failed to fetch git diff: {err}", file=sys.stderr)
        return ""


def parse_diff(diff_text: str) -> Dict[str, Set[int]]:
    """Parse git diff output to find added/modified lines in files.

    Args:
        diff_text: Raw diff text from git.

    Returns:
        Dictionary mapping relative file paths to sets of modified line numbers.
    """
    changed_lines: Dict[str, Set[int]] = {}
    current_file = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            # Extract target file path (skipping 'b/')
            current_file = line[6:].strip()
            changed_lines[current_file] = set()
        elif line.startswith("@@ ") and current_file is not None:
            # Extract line number ranges (e.g., +15,3 or +15)
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start = int(match.group(1))
                count = int(match.group(2)) if match.group(2) else 1
                for offset in range(count):
                    changed_lines[current_file].add(start + offset)

    # Filter out empty entries or files that don't exist/aren't Python
    active_changes = {}
    for filepath, lines in changed_lines.items():
        if lines and filepath.endswith(".py"):
            active_changes[filepath] = lines

    return active_changes


def check_coverage_gaps(
    repo_root: str,
    changed_files: Dict[str, Set[int]],
    cov_db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Check test coverage gaps for changed files.

    Args:
        repo_root: Path to the repo root.
        changed_files: Dict mapping relative files to changed lines.
        cov_db_path: Path to the coverage db (defaults to standard .coverage).

    Returns:
        A list of dictionaries containing gap stats per file.
    """
    gaps_report = []

    # Configure and load coverage database
    cov = coverage.Coverage(data_file=cov_db_path)
    try:
        cov.load()
    except Exception as err:  # pylint: disable=broad-except
        print(f"Warning: Could not load coverage database: {err}", file=sys.stderr)
        # Continue with empty coverage (meaning all lines are gaps)

    cov_data = cov.get_data()

    for rel_path, modified_lines in sorted(changed_files.items()):
        abs_path = os.path.normpath(os.path.join(repo_root, rel_path))

        # Retrieve executed lines from coverage database
        # Coverage stores paths as absolute, but handles casing/normalizations.
        executed_lines = set(cov_data.lines(abs_path) or [])

        # Gaps are modified lines that were not executed
        missing_lines = sorted(list(modified_lines - executed_lines))

        covered_count = len(modified_lines) - len(missing_lines)
        pct = (covered_count / len(modified_lines)) * 100 if modified_lines else 0.0

        gaps_report.append(
            {
                "file": rel_path,
                "total_changed": len(modified_lines),
                "covered_changed": covered_count,
                "uncovered_lines": missing_lines,
                "coverage_pct": pct,
            }
        )

    return gaps_report


def print_report(reports: List[Dict[str, Any]], format_type: str = "text") -> None:
    """Print the test gap report.

    Args:
        reports: List of test gap data per file.
        format_type: Output format ('text' or 'markdown').
    """
    # Sort: lowest coverage percentage first, then most uncovered lines
    reports.sort(
        key=lambda x: (x["coverage_pct"], -len(x["uncovered_lines"]), x["file"])
    )

    if format_type == "markdown":
        print("# Test Coverage Gap Report\n")
        print(
            "| File | Changed Lines | Covered | Uncovered | "
            "Gap % | Uncovered Line Details |"
        )
        print("|---|---|---|---|---|---|")
        for r in reports:
            gaps_str = (
                ", ".join(str(ln) for ln in r["uncovered_lines"])
                if r["uncovered_lines"]
                else "None"
            )
            print(
                f"| `{r['file']}` | {r['total_changed']} | {r['covered_changed']} | "
                f"{len(r['uncovered_lines'])} | {r['coverage_pct']:.1f}% | "
                f"`{gaps_str}` |"
            )
    else:
        print("=" * 80)
        print("                      TEST COVERAGE GAP REPORT")
        print("=" * 80)
        print(f"{'File':<45} {'Changed':<8} {'Covered':<8} {'Gap %':<8}")
        print("-" * 80)

        for r in reports:
            print(
                f"{r['file']:<45} {r['total_changed']:<8} "
                f"{r['covered_changed']:<8} {r['coverage_pct']:.1f}%"
            )
            if r["uncovered_lines"]:
                print(f"   Missing lines: {r['uncovered_lines']}")
                print("-" * 80)

        total_gaps = sum(len(r["uncovered_lines"]) for r in reports)
        print(
            f"\nSummary: Found {total_gaps} uncovered changed lines "
            f"across {len(reports)} files."
        )
        print("=" * 80)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="test-gap: Audit test coverage gaps for changed code."
    )
    parser.add_argument(
        "--diff-file",
        help="Path to a pre-saved unified diff file (instead of running git diff)",
    )
    parser.add_argument(
        "--ref",
        help="Git commit ref or branch to diff against (e.g. 'origin/main')",
    )
    parser.add_argument(
        "--cov-file",
        help="Path to the coverage database file (default: .coverage)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown"],
        default="text",
        help="Report output format",
    )

    args = parser.parse_args()

    repo_root = get_repo_root()

    diff_text = ""
    if args.diff_file:
        if os.path.exists(args.diff_file):
            with open(args.diff_file, "r", encoding="utf-8") as f:
                diff_text = f.read()
        else:
            print(f"Error: Diff file not found: {args.diff_file}", file=sys.stderr)
            sys.exit(1)
    else:
        diff_text = get_git_diff(args.ref)

    if not diff_text.strip():
        print("No code modifications detected (diff is empty).")
        sys.exit(0)

    changed_files = parse_diff(diff_text)
    if not changed_files:
        print("No modified Python (.py) files found in diff.")
        sys.exit(0)

    reports = check_coverage_gaps(repo_root, changed_files, args.cov_file)
    print_report(reports, args.format)

    # Exit with code 1 if there are any uncovered changed lines (gaps)
    has_gaps = any(len(r["uncovered_lines"]) > 0 for r in reports)
    sys.exit(1 if has_gaps else 0)


if __name__ == "__main__":
    main()

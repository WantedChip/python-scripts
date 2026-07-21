#!/usr/bin/env python3
"""Stash Manager.

Provides a consolidated git stash viewer detailing stash ages, source branches,
file modification summaries, and conflict risks before applying them.
"""

import argparse
import os
import re
import subprocess  # nosec B404
import sys
from typing import Any, Dict, List


def is_git_repo(path: str) -> bool:
    """Verify if path is inside a Git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        return res.returncode == 0
    except OSError:
        return False


def get_current_branch(path: str) -> str:
    """Get active Git branch name."""
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        return res.stdout.strip() or "HEAD detached"
    except (OSError, subprocess.SubprocessError):
        return "Unknown"


def get_stash_list(path: str) -> List[Dict[str, Any]]:
    """Parse output of git stash list to collect metadata."""
    stashes: List[Dict[str, Any]] = []
    try:
        res = subprocess.run(
            ["git", "stash", "list"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        lines = [line.strip() for line in res.stdout.split("\n") if line.strip()]
    except (OSError, subprocess.SubprocessError):
        return stashes

    for idx, line in enumerate(lines):
        parts = line.split(":", 2)
        if len(parts) >= 2:
            stash_id_str = parts[0].strip()
            desc = parts[1].strip()
            detail = parts[2].strip() if len(parts) > 2 else ""

            branch = "Unknown"
            branch_match = re.search(r"WIP on ([^\s:]+)|On ([^\s:]+)", desc)
            if branch_match:
                branch = branch_match.group(1) or branch_match.group(2)

            stashes.append(
                {
                    "index": idx,
                    "id": stash_id_str,
                    "branch": branch,
                    "description": f"{desc}: {detail}" if detail else desc,
                }
            )
    return stashes


def get_stash_details(path: str, stash_id: str) -> Dict[str, Any]:
    """Retrieve file lists, creation timestamp, and logs for a specific stash index."""
    details: Dict[str, Any] = {"date": "Unknown", "files": [], "diff": ""}

    try:
        res = subprocess.run(
            ["git", "show", "-s", "--format=%ci", stash_id],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        if res.returncode == 0:
            details["date"] = res.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        res = subprocess.run(
            ["git", "stash", "show", "--name-only", stash_id],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        if res.returncode == 0:
            details["files"] = [
                line.strip() for line in res.stdout.split("\n") if line.strip()
            ]
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        res = subprocess.run(
            ["git", "stash", "show", "-p", stash_id],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        if res.returncode == 0:
            details["diff"] = res.stdout
    except (OSError, subprocess.SubprocessError):
        pass

    return details


def evaluate_conflict_risk(path: str, stash_files: List[str]) -> str:
    """Evaluate conflict risk by comparing stash files with current local changes."""
    if not stash_files:
        return "None"

    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        local_changed = []
        for line in res.stdout.split("\n"):
            if len(line) > 3:
                local_changed.append(line[3:].strip())
    except (OSError, subprocess.SubprocessError):
        local_changed = []

    overlaps = set(stash_files) & set(local_changed)
    if overlaps:
        overlap_str = ", ".join(list(overlaps)[:2])
        return f"HIGH (Overlapping local changes in: {overlap_str})"

    return "Low"


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Explore git stashes with branch info, conflict checks, and previews."
        )
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Git repository folder path (default: current directory).",
    )
    parser.add_argument(
        "-p",
        "--preview",
        help="Preview stash details and diff (specify stash index e.g. 0).",
    )
    parser.add_argument(
        "-a", "--apply", help="Apply a stash safely (specify stash index e.g. 0)."
    )

    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.exists(repo_path):
        print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
        sys.exit(1)

    if not is_git_repo(repo_path):
        print(f"Error: '{repo_path}' is not inside a Git repository.", file=sys.stderr)
        sys.exit(1)

    if args.preview is not None:
        stash_id = f"stash@{{{args.preview}}}"
        details = get_stash_details(repo_path, stash_id)

        print(
            "========================================================================"
        )
        print(f"STASH DETAILS FOR: {stash_id}")
        print(
            "========================================================================"
        )
        print(f"Created: {details['date']}")
        print(f"Modified Files ({len(details['files'])}):")
        for f in details["files"]:
            print(f"  - {f}")
        print("-" * 80)
        print("Diff Preview:")
        print(details["diff"])
        print("=" * 80)
        sys.exit(0)

    if args.apply is not None:
        stash_id = f"stash@{{{args.apply}}}"
        details = get_stash_details(repo_path, stash_id)
        risk = evaluate_conflict_risk(repo_path, details["files"])

        print(f"Stash ID: {stash_id}")
        print(f"Conflict Risk: {risk}")

        if "HIGH" in risk:
            confirm = (
                input("Warning: High risk of merge conflicts. Apply anyway? [y/N]: ")
                .strip()
                .lower()
            )
            if confirm not in ("y", "yes"):
                print("Operation aborted.")
                sys.exit(0)

        try:
            print(f"Applying {stash_id}...")
            res = subprocess.run(
                ["git", "stash", "apply", stash_id],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )  # nosec B607, B603
            print(res.stdout)
            if res.returncode != 0:
                print(res.stderr, file=sys.stderr)
                sys.exit(res.returncode)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"Error: Failed to apply stash: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    stashes = get_stash_list(repo_path)
    current_branch = get_current_branch(repo_path)

    print("========================================================================")
    print(f"GIT STASHES AUDIT FOR: {repo_path}")
    print(f"Active Branch: {current_branch}")
    print("========================================================================")

    if not stashes:
        print("\n[+] No stashes found in this repository.")
        sys.exit(0)

    header = (
        f"{'INDEX':<6} | {'SOURCE BRANCH':<15} | {'CONFLICT RISK':<15} | "
        f"{'DESCRIPTION'}"
    )
    print(header)
    print("-" * 80)

    for s in stashes:
        details = get_stash_details(repo_path, s["id"])
        risk = evaluate_conflict_risk(repo_path, details["files"])

        risk_display = "Low"
        if "HIGH" in risk:
            risk_display = "HIGH"

        desc = s["description"]
        if len(desc) > 38:
            desc = desc[:35] + "..."

        print(f"{s['index']:<6} | {s['branch']:<15} | {risk_display:<15} | {desc}")

    print("=" * 80)
    print("To preview diff:  python stash_manager.py --preview <index>")
    print("To apply stash:   python stash_manager.py --apply <index>")
    print("=" * 80)


if __name__ == "__main__":
    main()

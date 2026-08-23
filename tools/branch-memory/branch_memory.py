#!/usr/bin/env python3
"""Branch Memory.

Scans local Git branches, extracts differences relative to the main branch,
searches for issues/TODOs in branch changes, and summarizes branch goals.
"""

import argparse
import os
import re
import subprocess  # nosec B404
import sys
from typing import Any, Dict, List, Tuple


def is_git_repo(path: str) -> bool:
    """Verify if target folder lies inside a Git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        return res.returncode == 0
    except OSError:
        return False


def get_main_branch(path: str) -> str:
    """Determine the primary main/master branch name of the repository."""
    try:
        res = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        if res.returncode == 0:
            return res.stdout.strip().split("/")[-1]
    except (OSError, ValueError):
        pass

    # Fallback checks
    for b in ("main", "master"):
        res = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{b}"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        if res.returncode == 0:
            return b
    return "main"


def get_branches(path: str) -> List[Tuple[str, str]]:
    """Fetch local branch names and relative creation/activity age details."""
    branches = []
    try:
        res = subprocess.run(
            ["git", "branch", "--format=%(refname:short)|%(committerdate:relative)"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        for line in res.stdout.split("\n"):
            if "|" in line:
                name, age = line.strip().split("|", 1)
                branches.append((name, age))
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        pass
    return branches


def get_branch_memory(path: str, branch: str, main_branch: str) -> Dict[str, Any]:
    """Compile commits summaries, diff file structures, and TODO flags."""
    info: Dict[str, Any] = {
        "commits": [],
        "files_modified": [],
        "todos": [],
        "issues": [],
    }

    # 1. Get recent 3 commits on this branch
    try:
        res = subprocess.run(
            ["git", "log", f"{main_branch}..{branch}", "-n", "3", "--oneline"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        info["commits"] = [
            line.strip() for line in res.stdout.split("\n") if line.strip()
        ]
        if not info["commits"]:
            res_last = subprocess.run(
                ["git", "log", "-n", "1", "--oneline", branch],
                cwd=path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )  # nosec
            info["commits"] = [
                line.strip() for line in res_last.stdout.split("\n") if line.strip()
            ]
    except (OSError, ValueError):
        pass

    # 2. Get modified files compared to main
    try:
        res = subprocess.run(
            ["git", "diff", "--name-status", f"{main_branch}...{branch}"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        info["files_modified"] = [
            line.strip() for line in res.stdout.split("\n") if line.strip()
        ]
    except (OSError, ValueError):
        pass

    # 3. Scan diff for TODO additions and issue refs
    try:
        res = subprocess.run(
            ["git", "diff", f"{main_branch}...{branch}"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        todo_pattern = re.compile(
            r"^\+\s*#?\s*(?:TODO|FIXME|BUG)\s*[:\-]?\s*(.*)", re.IGNORECASE
        )
        issue_pattern = re.compile(r"(?<!\w)(?:[A-Z]+-\d+|GH-\d+|#\d+)\b")

        for line in res.stdout.split("\n"):
            if line.startswith("+"):
                todo_match = todo_pattern.match(line)
                if todo_match:
                    info["todos"].append(todo_match.group(1).strip())
                for issue in issue_pattern.finditer(line):
                    info["issues"].append(issue.group(0))
    except (OSError, ValueError):
        pass

    info["issues"] = sorted(list(set(info["issues"])))
    return info


# pylint: disable=too-many-branches
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect git branches to summarize tasks, modifications, "
            "and active TODOs."
        )
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Git repository path to audit (default: current directory).",
    )

    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.exists(repo_path):
        print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
        sys.exit(1)

    if not is_git_repo(repo_path):
        print(f"Error: '{repo_path}' is not inside a Git repository.", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("BRANCH MEMORY: CONTEXT SUMMARY COLLECTOR")
    print("========================================================================")
    print(f"Repository: {repo_path}")

    main_branch = get_main_branch(repo_path)
    print(f"Main Branch: {main_branch}")
    print("Analyzing branches modifications and active annotations...")
    print("-" * 80)

    branches = get_branches(repo_path)
    if not branches:
        print("[-] No branches discovered.")
        sys.exit(0)

    for name, age in branches:
        if name == main_branch:
            print(f"Branch: {name} (Main Branch, last active {age})")
            print("  - Active tracking checkpoint.")
            print("-" * 80)
            continue

        mem = get_branch_memory(repo_path, name, main_branch)

        print(f"Branch: {name} (Last active {age})")

        if mem["commits"]:
            print("  Recent Commits:")
            for c in mem["commits"]:
                print(f"    - {c}")
        else:
            print("  Recent Commits: None (Branch matches main branch head)")

        if mem["files_modified"]:
            print(f"  Files Modified ({len(mem['files_modified'])}):")
            for f in mem["files_modified"][:3]:
                print(f"    - {f}")
            if len(mem["files_modified"]) > 3:
                print(f"    ... and {len(mem['files_modified']) - 3} more files.")
        else:
            print("  Files Modified: None")

        if mem["issues"]:
            print(f"  Linked Issues: {', '.join(mem['issues'])}")

        if mem["todos"]:
            print(f"  Unfinished TODOs/FIXMEs ({len(mem['todos'])}):")
            for todo in mem["todos"][:3]:
                print(f"    * {todo}")
            if len(mem["todos"]) > 3:
                print(f"    * ... and {len(mem['todos']) - 3} more.")

        print("-" * 80)


if __name__ == "__main__":
    main()

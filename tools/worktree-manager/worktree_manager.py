#!/usr/bin/env python3
"""Worktree Manager.

Provides a unified manager to list git worktrees, calculate their disk usages,
detect abandoned metadata, and safely add or clean them.
"""

import argparse
import os
import subprocess  # nosec B404
import sys
from typing import Any, Dict, List, Optional


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
        )  # nosec B607, B603
        return res.returncode == 0
    except OSError:
        return False


def get_dir_size(path: str) -> int:
    """Calculate absolute disk storage space used by a directory in bytes."""
    total = 0
    if not os.path.exists(path):
        return total
    try:
        for root, _, files in os.walk(path):
            for f in files:
                fpath = os.path.join(root, f)
                try:
                    total += os.path.getsize(fpath)
                except OSError:
                    pass
    except OSError:
        pass
    return total


def get_worktree_list(repo_path: str) -> List[Dict[str, Any]]:
    """Parse git worktree list outputs to compile directory paths and branches."""
    worktrees: List[Dict[str, Any]] = []
    try:
        res = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        if res.returncode != 0:
            return worktrees

        current: Dict[str, Any] = {}
        for line in res.stdout.split("\n"):
            line = line.strip()
            if not line:
                if current:
                    worktrees.append(current)
                    current = {}
                continue

            parts = line.split(" ", 1)
            key = parts[0]
            val = parts[1] if len(parts) > 1 else ""

            if key == "worktree":
                current["path"] = val
            elif key == "branch":
                current["branch"] = val.split("/")[-1] if "/" in val else val
            elif key == "commit":
                current["commit"] = val[:7]
        if current:
            worktrees.append(current)
    except (OSError, subprocess.SubprocessError):
        pass
    return worktrees


def run_list(repo_path: str) -> None:
    """Print Git worktrees, highlighting disk usage and orphan status."""
    worktrees = get_worktree_list(repo_path)
    if not worktrees:
        print("[-] No Git worktrees registered in this repository.")
        return

    print("========================================================================")
    print("GIT WORKTREES AUDIT")
    print("========================================================================")
    print(f"{'PATH':<28} | {'BRANCH':<15} | {'DISK SIZE':<12} | {'STATUS'}")
    print("-" * 80)

    for wt in worktrees:
        path = wt.get("path", "Unknown")
        branch = wt.get("branch", "N/A")

        status = "Active"
        size_str = "N/A"
        if not os.path.exists(path):
            status = "Abandoned (Folder deleted)"
        else:
            bytes_size = get_dir_size(path)
            size_str = f"{bytes_size / (1024*1024):.1f} MB"

        disp_path = path
        if len(disp_path) > 28:
            disp_path = "..." + disp_path[-25:]

        print(f"{disp_path:<28} | {branch:<15} | {size_str:<12} | {status}")
    print("=" * 80)
    print("Hint: Prune deleted worktrees using: python worktree_manager.py prune")


def run_add(repo_path: str, name: str, branch: Optional[str]) -> None:
    """Add a new git worktree located in the parent directory context."""
    parent_dir = os.path.dirname(repo_path)
    wt_path = os.path.join(parent_dir, name)

    if os.path.exists(wt_path):
        print(f"Error: Target path already exists: {wt_path}", file=sys.stderr)
        sys.exit(1)

    cmd = ["git", "worktree", "add", wt_path]
    if branch:
        cmd.append(branch)
    else:
        cmd.extend(["-b", name])

    print(f"Creating worktree '{name}' in: {wt_path}")
    try:
        res = subprocess.run(
            cmd,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        print(res.stdout.strip())
        if res.returncode != 0:
            print(res.stderr.strip(), file=sys.stderr)
            sys.exit(res.returncode)
        print("[+] Success: Worktree created.")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Error executing command: {e}", file=sys.stderr)


def run_prune(repo_path: str) -> None:
    """Prune stale git worktree administrative configurations."""
    print("Pruning stale worktrees metadata...")
    try:
        res = subprocess.run(
            ["git", "worktree", "prune"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        if res.returncode == 0:
            print("[+] Success: Stale worktree records pruned.")
        else:
            print(res.stderr.strip(), file=sys.stderr)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Error executing prune: {e}", file=sys.stderr)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Understand and manage Git worktrees with disk usage audit features."
        )
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute.")

    subparsers.add_parser(
        "list",
        help="List all active and abandoned git worktrees with storage space details.",
    )

    add_parser = subparsers.add_parser("add", help="Add a new Git worktree.")
    add_parser.add_argument("name", help="Directory name for the new worktree.")
    add_parser.add_argument(
        "branch",
        nargs="?",
        help="Existing branch to check out (creates new matching branch if omitted).",
    )

    subparsers.add_parser(
        "prune", help="Prune git metadata of deleted worktree folders."
    )

    args = parser.parse_args()

    repo_path = os.getcwd()
    if not is_git_repo(repo_path):
        print(
            f"Error: Current directory '{repo_path}' is not inside a Git repository.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.command == "list":
        run_list(repo_path)
    elif args.command == "add":
        run_add(repo_path, args.name, args.branch)
    elif args.command == "prune":
        run_prune(repo_path)
    else:
        run_list(repo_path)


if __name__ == "__main__":
    main()

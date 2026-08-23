#!/usr/bin/env python3
"""Stash Conflict Preview.

Estimates potential merge conflicts (file-level and line hunk overlaps) before
applying a Git stash to the current working tree.
"""

import argparse
import os
import re
import subprocess  # nosec B404
import sys
from typing import Dict, List, Tuple


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


def get_stashes(repo_path: str) -> List[str]:
    """Get the list of stashes in the repository."""
    try:
        res = subprocess.run(
            ["git", "stash", "list"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        return [line.strip() for line in res.stdout.split("\n") if line.strip()]
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        return []


def parse_diff_hunks(diff_output: str) -> Dict[str, List[Tuple[int, int]]]:
    """Parse unified diff content to extract changed files and line ranges.

    Returns:
        Dict mapping filename -> list of (start_line, end_line) ranges modified.
    """
    file_ranges: Dict[str, List[Tuple[int, int]]] = {}
    current_file = None

    lines = diff_output.split("\n")
    for line in lines:
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            file_ranges[current_file] = []
        elif line.startswith("@@ ") and current_file:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start = int(match.group(1))
                length = int(match.group(2)) if match.group(2) else 1
                file_ranges[current_file].append((start, start + length - 1))
    return file_ranges


def get_stash_diff_ranges(
    repo_path: str, stash_id: str
) -> Dict[str, List[Tuple[int, int]]]:
    """Retrieve line modification ranges inside a specific stash index."""
    try:
        res = subprocess.run(
            ["git", "diff", f"{stash_id}^1", stash_id],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        if res.returncode == 0 and res.stdout is not None:
            return parse_diff_hunks(res.stdout)
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        pass
    return {}


def get_local_diff_ranges(repo_path: str) -> Dict[str, List[Tuple[int, int]]]:
    """Retrieve line modification ranges inside active local working tree."""
    try:
        res = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        if res.returncode == 0 and res.stdout is not None:
            return parse_diff_hunks(res.stdout)
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        pass
    return {}


def get_head_diff_ranges(
    repo_path: str, stash_id: str
) -> Dict[str, List[Tuple[int, int]]]:
    """Retrieve line modifications between stash base and current HEAD."""
    try:
        res = subprocess.run(
            ["git", "diff", f"{stash_id}^1", "HEAD"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        if res.returncode == 0 and res.stdout is not None:
            return parse_diff_hunks(res.stdout)
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        pass
    return {}


def check_ranges_overlap(
    r1: List[Tuple[int, int]], r2: List[Tuple[int, int]]
) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """Identify if line ranges overlap, returning list of conflict coordinates."""
    overlaps = []
    for s1, e1 in r1:
        for s2, e2 in r2:
            if (s1 - 2 <= e2) and (e1 + 2 >= s2):
                overlaps.append(((s1, e1), (s2, e2)))
    return overlaps


# pylint: disable=too-many-locals,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Preview potential line overlaps and merge conflicts before git "
            "stash apply."
        )
    )
    parser.add_argument(
        "stash_index",
        type=int,
        nargs="?",
        default=0,
        help="Git stash list index to preview (default: 0).",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Git repository path to query (default: current directory).",
    )

    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    if not os.path.exists(repo_path):
        print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
        sys.exit(1)

    if not is_git_repo(repo_path):
        print(f"Error: '{repo_path}' is not inside a Git repository.", file=sys.stderr)
        sys.exit(1)

    # 1. Fetch stashes
    stashes = get_stashes(repo_path)
    if not stashes:
        print("\n[+] No stashes found in this repository.")
        sys.exit(0)

    if args.stash_index >= len(stashes):
        max_idx = len(stashes) - 1
        print(
            f"Error: Stash index {args.stash_index} is out of range. "
            f"Max index: {max_idx}",
            file=sys.stderr,
        )
        sys.exit(1)

    stash_id = f"stash@{{{args.stash_index}}}"
    print("========================================================================")
    print(f"STASH CONFLICT PREVIEW FOR: {stash_id}")
    print(f"Target: {stashes[args.stash_index]}")
    print("========================================================================")
    print(
        "Analyzing stash line modifications vs current HEAD commits & working tree..."
    )
    print("-" * 80)

    # 2. Extract ranges
    stash_diff = get_stash_diff_ranges(repo_path, stash_id)

    if not stash_diff:
        print(
            "[-] No code modifications found in target stash (may contain only "
            "untracked files)."
        )
        sys.exit(0)

    local_diff = get_local_diff_ranges(repo_path)
    head_diff = get_head_diff_ranges(repo_path, stash_id)

    conflicts_found = False

    for filename, stash_ranges in stash_diff.items():
        print(f"Auditing file: {filename}")

        # Check against local modifications
        local_ranges = local_diff.get(filename, [])
        local_overlaps = check_ranges_overlap(stash_ranges, local_ranges)

        # Check against commits added since stash
        head_ranges = head_diff.get(filename, [])
        head_overlaps = check_ranges_overlap(stash_ranges, head_ranges)

        if local_overlaps or head_overlaps:
            conflicts_found = True
            print("  [!] LIKELY MERGE CONFLICT DETECTED!")
            for stash_r, local_r in local_overlaps:
                msg_loc = (
                    f"    - Overlaps local unstaged changes: stash lines "
                    f"{stash_r[0]}-{stash_r[1]} vs local lines "
                    f"{local_r[0]}-{local_r[1]}"
                )
                print(msg_loc)
            for stash_r, head_r in head_overlaps:
                msg_head = (
                    f"    - Overlaps commits made since stash: stash lines "
                    f"{stash_r[0]}-{stash_r[1]} vs head changes lines "
                    f"{head_r[0]}-{head_r[1]}"
                )
                print(msg_head)
        else:
            print("  [+] Clean merge predicted.")
        print("-" * 80)

    print("\n" + "=" * 80)
    print("SUMMARY DIAGNOSTICS:")
    if conflicts_found:
        print(
            "  Status: HIGH RISK. Overlapping hunks detected. Merge conflicts "
            "are highly likely."
        )
        print("  Hint: commit or stash your current local changes before applying.")
    else:
        print(
            "  Status: CLEAN. No overlapping modifications detected. Ready to "
            "apply safely."
        )
    print("=" * 80)


if __name__ == "__main__":
    main()

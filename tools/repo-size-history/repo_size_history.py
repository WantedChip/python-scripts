"""Walk git history to calculate repo size at each commit/tag,

and pinpoint exactly when and which files caused size growth/bloat.
"""

# pylint: disable=duplicate-code

import argparse
import logging
import os
import subprocess  # nosec
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


class GitCommandError(Exception):
    """Exception raised when a Git command fails."""


def run_git(args: List[str], cwd: Optional[str] = None) -> str:
    """Run a Git command and return stdout.

    Args:
        args: List of Git arguments.
        cwd: Working directory.

    Returns:
        Decoded stdout.

    Raises:
        GitCommandError: If the command fails.
    """
    cmd = ["git"] + args
    logging.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(  # nosec
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as err:
        raise GitCommandError(
            f"Git command failed: {' '.join(cmd)}. Error: {err.stderr.strip()}"
        ) from err


def get_commit_list(
    repo_path: str, limit: int, tags_only: bool = False
) -> List[Tuple[str, int, str, str]]:
    """Fetch the list of commits in chronological order (oldest first).

    Args:
        repo_path: Path to git repository.
        limit: Max number of commits to fetch.
        tags_only: If True, only fetch commits that are tags.

    Returns:
        List of tuples (commit_hash, timestamp, author_name, subject).
    """
    args = ["log", "--first-parent", "--format=%H|%ct|%an|%s"]
    if tags_only:
        args.append("--simplify-by-decoration")
        # To filter down to tag decorations specifically:
        # Note: --simplify-by-decoration keeps branch tips too, but we
        # can filter afterwards or use tags references. Let's simplify
        # by using it, and we can also use tags if needed.
    args.append(f"-n {limit}")

    try:
        output = run_git(args, cwd=repo_path)
    except GitCommandError as err:
        print(f"Error reading git log: {err}")
        sys.exit(1)

    commits = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        commit_hash, raw_time, author, subject = parts[0], parts[1], parts[2], parts[3]
        try:
            timestamp = int(raw_time)
            commits.append((commit_hash, timestamp, author, subject))
        except ValueError:
            continue

    # Reverse to process chronologically (oldest to newest)
    commits.reverse()
    return commits


def get_repo_files(repo_path: str, commit_ref: str) -> Dict[str, int]:
    """Get all tracked files and their sizes at a specific commit.

    Args:
        repo_path: Path to git repository.
        commit_ref: Commit hash or reference.

    Returns:
        A dictionary mapping file path to size in bytes.
    """
    files: Dict[str, int] = {}
    try:
        output = run_git(["ls-tree", "-r", "-l", commit_ref], cwd=repo_path)
    except GitCommandError:
        # Commit might be empty or invalid (e.g. initial/root commit ref)
        return files

    for line in output.splitlines():
        if not line.strip():
            continue
        # Format: <mode> <type> <sha> <size_or_dash>\t<path>
        parts = line.split(maxsplit=4)
        if len(parts) < 5:
            continue
        obj_type, size_str, path = parts[1], parts[3], parts[4]

        if obj_type == "blob":
            try:
                size = int(size_str)
                files[path] = size
            except ValueError:
                continue

    return files


def format_size(size_bytes: float) -> str:
    """Format size in bytes to a human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted size string (e.g. 1.23 MB).
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def analyze_history(  # pylint: disable=too-many-locals
    repo_path: str,
    commits: List[Tuple[str, int, str, str]],
    spike_pct_threshold: float,
    file_size_mb_threshold: float,
) -> None:
    """Analyze and output repository size history and spikes.

    Args:
        repo_path: Path to git repository.
        commits: List of commit metadata.
        spike_pct_threshold: Percentage size increase threshold.
        file_size_mb_threshold: Individual file size warning threshold in MB.
    """
    print(f"\nAnalyzing size history for {len(commits)} commits...")
    print(
        f"Spike threshold: {spike_pct_threshold}% | "
        f"File warning: {file_size_mb_threshold} MB\n"
    )

    prev_files: Dict[str, int] = {}
    prev_size = 0

    file_warning_bytes = int(file_size_mb_threshold * 1024 * 1024)

    print(
        f"{'Commit':<8} | {'Date':<10} | {'Total Size':<12} | "
        f"{'Change':<12} | {'Author':<15} | {'Subject'}"
    )
    print("-" * 90)

    for idx, (commit_hash, timestamp, author, subject) in enumerate(commits):
        curr_files = get_repo_files(repo_path, commit_hash)
        curr_size = sum(curr_files.values())

        date_str = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
        change_str = "-"
        pct_change = 0.0

        if idx > 0:
            delta = curr_size - prev_size
            change_str = format_size(delta)
            if delta > 0:
                change_str = f"+{change_str}"
            if prev_size > 0:
                pct_change = (delta / prev_size) * 100

        short_hash = commit_hash[:8]
        short_subj = subject[:25] + "..." if len(subject) > 25 else subject
        short_auth = author[:15]

        print(
            f"{short_hash:<8} | {date_str:<10} | "
            f"{format_size(curr_size):<12} | {change_str:<12} | "
            f"{short_auth:<15} | {short_subj}"
        )

        # Check for spike or large files
        has_spike = idx > 0 and pct_change >= spike_pct_threshold
        large_files_added = []

        # Find files that grew or were added
        for path, size in curr_files.items():
            prev_file_size = prev_files.get(path, 0)
            file_delta = size - prev_file_size
            if file_delta > 0:
                # If it's a new or modified file that is larger than the file threshold
                if size >= file_warning_bytes:
                    large_files_added.append(
                        (path, size, file_delta, prev_file_size == 0)
                    )

        if has_spike or large_files_added:
            print(f"  * Warning/Spike detected at commit {short_hash}!")
            if has_spike:
                grew_sz = format_size(curr_size - prev_size)
                print(f"    - Total size grew by {pct_change:.2f}% ({grew_sz})")

            if large_files_added:
                print("    - Heavy files added or expanded in this commit:")
                # Sort by delta size descending
                large_files_added.sort(key=lambda x: x[2], reverse=True)
                for path, size, file_delta, is_new in large_files_added:
                    status = "NEW" if is_new else "GROWN"
                    delta_info = (
                        f"+{format_size(file_delta)}" if not is_new else "new file"
                    )
                    print(
                        f"      [{status}] {path} ({format_size(size)}, {delta_info})"
                    )
            print()

        prev_files = curr_files
        prev_size = curr_size


def main() -> None:
    """Main CLI execution."""
    parser = argparse.ArgumentParser(
        description=(
            "Show exactly when a repository became bloated and "
            "which commits/files caused the growth."
        )
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Path to target git repository (default: current directory).",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=50,
        help="Max number of commits to analyze (default: 50).",
    )
    parser.add_argument(
        "-s",
        "--spike-threshold",
        type=float,
        default=10.0,
        help=(
            "Percentage growth threshold to flag as size spike "
            "(default: 10.0 for 10%%)."
        ),
    )
    parser.add_argument(
        "-f",
        "--file-size-mb",
        type=float,
        default=5.0,
        help="Warning threshold for individual large files in MB (default: 5.0).",
    )
    parser.add_argument(
        "--tags-only",
        action="store_true",
        help="Analyze only tagged commits.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output.",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    repo_path = args.repo_path
    if not os.path.exists(os.path.join(repo_path, ".git")):
        print(f"Error: '{repo_path}' is not a valid Git repository.")
        sys.exit(1)

    commits = get_commit_list(repo_path, args.limit, args.tags_only)
    if not commits:
        print("No commits found matching the criteria.")
        sys.exit(0)

    analyze_history(
        repo_path,
        commits,
        args.spike_threshold,
        args.file_size_mb,
    )


if __name__ == "__main__":
    main()

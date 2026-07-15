"""Git Time Machine.

Automates Git history investigations to find when config values changed,
when dependencies were introduced, and when files grew beyond size limits.
"""

import argparse
import re
import subprocess  # nosec B404
import sys

# pylint: disable=duplicate-code
from typing import Dict, List, Optional


def run_git(args: List[str]) -> str:
    """Runs a git command and returns its standard output.

    Args:
        args: Git subcommand and parameters list.

    Returns:
        Standard output string of the command.

    Raises:
        RuntimeError: If Git command fails or is not found.
    """
    try:
        # pylint: disable=subprocess-run-check
        res = subprocess.run(  # nosec B603
            ["git"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip())
        return res.stdout
    except (FileNotFoundError, OSError) as err:
        raise RuntimeError(f"Git command execution failed: {err}") from err


def parse_commit_diffs(log_output: str) -> List[Dict[str, str]]:
    """Parses git log output with diff details into structured records.

    Args:
        log_output: Raw git log string.

    Returns:
        List of dictionaries with commit metadata and diff details.
    """
    # pylint: disable=too-many-branches
    commits = []
    current_commit: Dict[str, str] = {}
    diff_lines: List[str] = []

    commit_re = re.compile(r"^commit\s+([a-f0-9]{40})")
    author_re = re.compile(r"^Author:\s+(.*)")
    date_re = re.compile(r"^Date:\s+(.*)")

    lines = log_output.splitlines()
    for line in lines:
        c_match = commit_re.match(line)
        if c_match:
            if current_commit:
                current_commit["diff"] = "\n".join(diff_lines)
                commits.append(current_commit)
            current_commit = {
                "hash": c_match.group(1),
                "author": "",
                "date": "",
                "message": "",
            }
            diff_lines = []
            continue

        a_match = author_re.match(line)
        if a_match and current_commit:
            current_commit["author"] = a_match.group(1).strip()
            continue

        d_match = date_re.match(line)
        if d_match and current_commit:
            current_commit["date"] = d_match.group(1).strip()
            continue

        # Check commit message body
        if current_commit and not current_commit["message"] and line.startswith("    "):
            current_commit["message"] = line.strip()
            continue

        # Collect diff lines
        if current_commit and (line.startswith("+") or line.startswith("-")):
            if not line.startswith("+++") and not line.startswith("---"):
                diff_lines.append(line)

    if current_commit:
        current_commit["diff"] = "\n".join(diff_lines)
        commits.append(current_commit)

    return commits


def find_config_change(pattern: str, filepath: str) -> None:
    """Finds commits that modified a config pattern in a specific file.

    Args:
        pattern: Config key or pattern to search.
        filepath: File path to investigate.
    """
    print(
        f"Searching history of '{filepath}' for config change "
        f"matching '{pattern}'..."
    )
    try:
        # Search using -G (regex matching changes) and include patch output
        output = run_git(["log", "-p", f"-G{pattern}", "--", filepath])
        commits = parse_commit_diffs(output)

        if not commits:
            print("No config changes found matching the pattern.")
            return

        for commit in commits:
            print("-" * 50)
            print(f"Commit:  {commit['hash'][:8]}")
            print(f"Author:  {commit['author']}")
            print(f"Date:    {commit['date']}")
            print(f"Message: {commit['message']}")
            print("Changes:")
            for line in commit["diff"].splitlines():
                if pattern in line:
                    print(f"  {line}")
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


def find_dependency_introduction(package: str, filepath: Optional[str]) -> None:
    """Finds when a dependency package was introduced or modified.

    Args:
        package: Package name to investigate.
        filepath: Optional path to dependency file.
    """
    # pylint: disable=too-many-nested-blocks
    # Auto-detect standard dependency files if none specified
    files_to_check = (
        [filepath]
        if filepath
        else [
            "requirements.txt",
            "package.json",
            "Cargo.toml",
            "pyproject.toml",
            "setup.py",
            "Gemfile",
        ]
    )

    found = False
    for fpath in files_to_check:
        # Only check files that exist in working tree or git index
        try:
            run_git(["log", "-1", "--", fpath])
        except RuntimeError:
            continue

        print(f"Searching history of '{fpath}' for package '{package}'...")
        try:
            output = run_git(["log", "-p", f"-S{package}", "--", fpath])
            commits = parse_commit_diffs(output)
            if commits:
                found = True
                for commit in commits:
                    print("-" * 50)
                    print(f"Commit:  {commit['hash'][:8]}")
                    print(f"Author:  {commit['author']}")
                    print(f"Date:    {commit['date']}")
                    print(f"Message: {commit['message']}")
                    print(f"Changes in {fpath}:")
                    for line in commit["diff"].splitlines():
                        if package in line:
                            print(f"  {line}")
        except RuntimeError as err:
            print(f"Error checking {fpath}: {err}", file=sys.stderr)

    if not found:
        print(f"No introduction record found for package '{package}'.")


def parse_size(size_str: str) -> int:
    """Parses human-readable size string (e.g. 500KB, 1MB) to bytes.

    Args:
        size_str: Size string with unit.

    Returns:
        Size in bytes.
    """
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$", size_str.strip())
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")

    value = float(match.group(1))
    unit = match.group(2).upper()

    multipliers = {
        "": 1,
        "B": 1,
        "KB": 1024,
        "K": 1024,
        "MB": 1024 * 1024,
        "M": 1024 * 1024,
        "GB": 1024 * 1024 * 1024,
        "G": 1024 * 1024 * 1024,
    }

    if unit not in multipliers:
        raise ValueError(f"Unknown size unit: {unit}")

    return int(value * multipliers[unit])


def format_bytes(bytes_count: int) -> str:
    """Formats bytes count to a human-readable size string.

    Args:
        bytes_count: Quantity in bytes.

    Returns:
        Formatted size string.
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_count < 1024.0:
            return f"{bytes_count:.2f} {unit}"
        bytes_count //= 1024
    return f"{bytes_count:.2f} TB"


def find_file_growth(filepath: str, threshold_str: str) -> None:
    """Analyzes file size growth milestones across Git commits.

    Args:
        filepath: File path to analyze.
        threshold_str: Human-readable size threshold.
    """
    # pylint: disable=too-many-branches,too-many-statements
    try:
        threshold = parse_size(threshold_str)
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Tracking size growth of '{filepath}' in Git history "
        f"(threshold: {threshold_str})..."
    )

    try:
        # Get list of all commits that touched the file, from oldest to newest
        log_out = run_git(["log", "--reverse", "--format=%H|%ad|%s", "--", filepath])
        lines = [line.strip() for line in log_out.splitlines() if line.strip()]

        if not lines:
            print(f"No Git history found for file '{filepath}'.")
            return

        exceeded = False
        prev_size = 0

        for line in lines:
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            commit_hash, date_str, msg = parts

            # Get file size at this commit
            try:
                size_out = run_git(["cat-file", "-s", f"{commit_hash}:{filepath}"])
                size = int(size_out.strip())
            except RuntimeError:
                # File might not exist in this commit (e.g. deleted or renamed)
                continue

            if size > threshold and not exceeded:
                print("-" * 50)
                print(">>> Milestone: File size exceeded threshold! <<<")
                print(f"Commit:      {commit_hash[:8]}")
                print(f"Date:        {date_str}")
                print(f"Message:     {msg}")
                print(
                    f"New Size:    {format_bytes(size)} "
                    f"(increased from {format_bytes(prev_size)})"
                )
                exceeded = True
            elif size > threshold:
                print(
                    f"  Commit {commit_hash[:8]} ({date_str}): "
                    f"Size is {format_bytes(size)}"
                )

            prev_size = size

        if not exceeded:
            print(
                f"File never exceeded {threshold_str}. "
                f"Current size: {format_bytes(prev_size)}"
            )

    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


def general_search(query: str) -> None:
    """Searches Git history for when a query string was added or removed.

    Args:
        query: Search string to match in commit patches.
    """
    print(f"Searching Git commit patches for string '{query}'...")
    try:
        output = run_git(["log", "-p", f"-S{query}"])
        commits = parse_commit_diffs(output)

        if not commits:
            print("No commits found matching the search query.")
            return

        for commit in commits:
            print("-" * 50)
            print(f"Commit:  {commit['hash'][:8]}")
            print(f"Author:  {commit['author']}")
            print(f"Date:    {commit['date']}")
            print(f"Message: {commit['message']}")
            print("Matching changes:")
            for line in commit["diff"].splitlines():
                if query in line:
                    print(f"  {line}")
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """CLI entry point for git-time-machine."""
    # pylint: disable=duplicate-code
    parser = argparse.ArgumentParser(
        description=(
            "Automate Git history investigations for changes, "
            "dependencies, and file growth."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Config subcommand
    config_parser = subparsers.add_parser(
        "config", help="Find when a config key or pattern changed."
    )
    config_parser.add_argument(
        "-p", "--pattern", required=True, help="Config key or pattern to search."
    )
    config_parser.add_argument(
        "-f", "--file", required=True, help="File path to investigate."
    )

    # Dependency subcommand
    dep_parser = subparsers.add_parser(
        "dependency", help="Find when a dependency package was introduced."
    )
    dep_parser.add_argument(
        "-n", "--name", required=True, help="Package name to search."
    )
    dep_parser.add_argument(
        "-f", "--file", help="Specific dependency file to search (optional)."
    )

    # File size subcommand
    size_parser = subparsers.add_parser(
        "file-size", help="Find when a file exceeded a size threshold."
    )
    size_parser.add_argument(
        "-f", "--file", required=True, help="File path to investigate."
    )
    size_parser.add_argument(
        "-t",
        "--threshold",
        required=True,
        help="Size threshold to check (e.g. 500KB, 1MB, 100K, 2M).",
    )

    # Search subcommand
    search_parser = subparsers.add_parser(
        "search", help="Search Git commit patches for additions/removals of a string."
    )
    search_parser.add_argument(
        "-q", "--query", required=True, help="Search string to match."
    )

    args = parser.parse_args()

    if args.command == "config":
        find_config_change(args.pattern, args.file)
    elif args.command == "dependency":
        find_dependency_introduction(args.name, args.file)
    elif args.command == "file-size":
        find_file_growth(args.file, args.threshold)
    elif args.command == "search":
        general_search(args.query)


if __name__ == "__main__":
    main()

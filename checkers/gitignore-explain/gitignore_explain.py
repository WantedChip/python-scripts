"""Explain why a file is ignored by Git, detailing the exact rule,

source file, line number, and instructions on how to unignore/fix it.
"""

# pylint: disable=duplicate-code

import argparse
import logging
import os
import re
import subprocess  # nosec
import sys
from typing import List, Optional, Tuple


def run_git(args: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
    """Run a Git command and return exit code, stdout, and stderr.

    Args:
        args: List of Git arguments (e.g. ['check-ignore', '-v', 'file.txt']).
        cwd: Directory in which to run the command.

    Returns:
        A tuple of (exit_code, stdout, stderr).
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
            check=False,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.SubprocessError as err:
        logging.error("Git subprocess execution failed: %s", err)
        return -1, "", str(err)


def is_git_repo(repo_path: str) -> bool:
    """Check if the path is inside a valid Git repository.

    Args:
        repo_path: Directory path.

    Returns:
        True if it is a Git repo, False otherwise.
    """
    code, _, _ = run_git(["rev-parse", "--is-inside-work-tree"], cwd=repo_path)
    return code == 0


def get_git_root(repo_path: str) -> Optional[str]:
    """Find the top-level directory of the Git repository.

    Args:
        repo_path: Directory path.

    Returns:
        The absolute path to the Git root directory, or None.
    """
    code, stdout, _ = run_git(["rev-parse", "--show-toplevel"], cwd=repo_path)
    if code == 0 and stdout:
        return os.path.abspath(stdout)
    return None


def check_tracked(repo_path: str, file_path: str) -> bool:
    """Check if a file is tracked by Git.

    Args:
        repo_path: Path to target git repository.
        file_path: Relative or absolute path to the file.

    Returns:
        True if the file is tracked, False otherwise.
    """
    # Use ls-files to verify if git is tracking this path
    code, stdout, _ = run_git(["ls-files", "--error-unmatch", file_path], cwd=repo_path)
    return code == 0 and bool(stdout)


# pylint: disable=too-many-statements
def explain_ignore(repo_path: str, file_path: str) -> None:
    """Analyze and print why the given path is ignored or not.

    Args:
        repo_path: Repository path.
        file_path: File path to check.
    """
    if not is_git_repo(repo_path):
        print(f"Error: '{repo_path}' is not a Git repository.")
        sys.exit(1)

    # Check if tracked first
    if check_tracked(repo_path, file_path):
        print(f"File: {file_path}")
        print("Status: NOT IGNORED (File is currently tracked by Git).")
        print("\nNote: Git ignore rules only apply to untracked files.")
        print("If you want Git to ignore this file, you must untrack it first:")
        print(f"  git rm --cached {file_path}")
        return

    # Check ignore rules
    code, stdout, stderr = run_git(["check-ignore", "-v", file_path], cwd=repo_path)

    if code != 0:
        if stderr:
            print(f"Git check-ignore failed: {stderr}")
            sys.exit(1)
        print(f"File: {file_path}")
        print("Status: NOT IGNORED (No ignore rules match this path).")
        return

    # Parse stdout: <source>:<line>:<pattern> <path>
    # Handle Windows drive letters in the source path (e.g. C:\path\.gitignore:3:*.txt)
    pattern = r"^(?P<source>.*?):(?P<line>\d+):(?P<pattern>.*?)\s+(?P<path>.*)$"
    match = re.match(pattern, stdout)

    if not match:
        print(f"Could not parse git check-ignore output: {stdout}")
        sys.exit(1)

    source = match.group("source")
    line_num = match.group("line")
    rule_pattern = match.group("pattern")

    print(f"File:   {file_path}")
    print("Status: IGNORED")
    print(f"Rule:   '{rule_pattern}'")
    print(f"Source: {source} (Line {line_num})")

    # Offer instructions to unignore
    print("\nHow to fix / unignore:")
    abs_source = (
        os.path.abspath(os.path.join(repo_path, source))
        if not os.path.isabs(source)
        else source
    )

    # Determine relative path from git root for exemption
    git_root = get_git_root(repo_path)
    rel_path_to_exempt = file_path
    if git_root:
        abs_file = os.path.abspath(os.path.join(repo_path, file_path))
        if abs_file.startswith(git_root):
            rel_path_to_exempt = os.path.relpath(abs_file, git_root).replace(
                os.sep, "/"
            )

    if ".git/info/exclude" in source:
        print(f"1. Open the local Git exclude file: {abs_source}")
        print(f"   Remove or comment out line {line_num} containing: {rule_pattern}")
    elif ".gitignore" in source:
        print(f"1. Open the ignore file: {abs_source}")
        print(f"   Remove or comment out line {line_num} containing: {rule_pattern}")
        print("OR")
        print("2. Add an exception rule to your repository's root `.gitignore`:")
        print(f"   !/{rel_path_to_exempt}")
    else:
        # Global ignore file
        print(f"1. Open your global ignore file: {abs_source}")
        print(f"   Remove or comment out line {line_num} containing: {rule_pattern}")
        print("OR")
        print("2. Add a local exception override to your repository's `.gitignore`:")
        print(f"   !/{rel_path_to_exempt}")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Explain why a file is ignored by Git, with "
            "instructions on how to unignore it."
        )
    )
    parser.add_argument(
        "file_path",
        help="Path to the file or directory to check.",
    )
    parser.add_argument(
        "-r",
        "--repo",
        default=".",
        help="Path to the Git repository (default: current directory).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging output.",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    explain_ignore(args.repo, args.file_path)


if __name__ == "__main__":
    main()

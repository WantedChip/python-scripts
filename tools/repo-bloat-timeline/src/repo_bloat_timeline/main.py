"""Repository Bloat Timeline Tool.

Scans Git repository commit history to identify exactly when a repository grew in size,
which commits caused size spikes, and which files contributed most to repository bloat.
"""

# pylint: disable=duplicate-code

import argparse
import json
import logging
import os
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class BloatFile:
    """Information about a file that contributed to commit bloat."""

    path: str
    size_bytes: int
    action: str


@dataclass
class BloatCommit:
    """Information about a commit that caused repository bloat."""

    commit_hash: str
    author: str
    date: str
    subject: str
    net_bytes_added: int
    large_files: List[BloatFile]


class GitRunner:  # pylint: disable=too-few-public-methods
    """Helper class to execute Git commands safely."""

    def __init__(self, repo_path: str) -> None:
        """Initialize GitRunner with target repository path.

        Args:
            repo_path: Path to the root or subfolder of a Git repository.
        """
        self.repo_path = os.path.abspath(repo_path)

    def run_git(self, args: List[str]) -> str:
        """Execute a git command in the target repository.

        Args:
            args: Command line arguments to pass to git.

        Returns:
            Standard output of the git command.

        Raises:
            RuntimeError: If git fails or path is not a git repository.
        """
        if not shutil.which("git"):
            raise RuntimeError("Git executable not found in PATH.")

        cmd = ["git", "-C", self.repo_path] + args
        try:
            result = subprocess.run(  # nosec B603
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except Exception as exc:
            err = str(exc)
            raise RuntimeError(f"Git command failed ({' '.join(cmd)}): {err}") from exc


def parse_commit_log(
    git_runner: GitRunner, revision: str, max_commits: int
) -> List[Dict[str, str]]:
    """Fetch raw commit history log from git.

    Args:
        git_runner: Helper instance to run git commands.
        revision: Target git revision range or branch name.
        max_commits: Maximum number of commits to scan.

    Returns:
        List of dictionaries containing commit metadata.
    """
    fmt = "%H%x1f%an%x1f%ad%x1f%s"
    log_output = git_runner.run_git(
        [
            "log",
            f"-n{max_commits}",
            f"--format={fmt}",
            "--date=iso-strict",
            revision,
        ]
    )

    if not log_output:
        return []

    commits: List[Dict[str, str]] = []
    for line in log_output.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append(
                {
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "subject": parts[3],
                }
            )
    return commits


def analyze_commit_bloat(  # pylint: disable=too-many-locals
    git_runner: GitRunner, commit_hash: str, threshold_bytes: int
) -> Tuple[int, List[BloatFile]]:
    """Analyze size additions and file changes for a single commit.

    Args:
        git_runner: Helper instance to run git commands.
        commit_hash: Commit hash string to inspect.
        threshold_bytes: File size threshold in bytes to consider as large file.

    Returns:
        Tuple of (net_bytes_added, list of large files).
    """
    diff_output = git_runner.run_git(
        ["diff-tree", "-r", "--no-commit-id", "--numstat", commit_hash]
    )

    net_bytes = 0
    large_files: List[BloatFile] = []

    for line in diff_output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            added_str, deleted_str, file_path = parts[0], parts[1], parts[2]
            if added_str.isdigit() and deleted_str.isdigit():
                # Text file line diff estimate (approx 40 bytes per line)
                added_lines = int(added_str)
                deleted_lines = int(deleted_str)
                line_delta = (added_lines - deleted_lines) * 40
                net_bytes += line_delta
            elif added_str == "-" and deleted_str == "-":
                # Binary file addition/modification: fetch exact object size
                action = "added"
                try:
                    obj_size_str = git_runner.run_git(
                        ["cat-file", "-s", f"{commit_hash}:{file_path}"]
                    )
                    size = int(obj_size_str)
                except RuntimeError:
                    size = 0
                    action = "modified"

                net_bytes += size
                if size >= threshold_bytes:
                    large_files.append(
                        BloatFile(path=file_path, size_bytes=size, action=action)
                    )

    return net_bytes, large_files


def find_repo_bloat_timeline(
    repo_path: str,
    revision: str = "HEAD",
    max_commits: int = 500,
    threshold_mb: float = 1.0,
    top_n: int = 10,
) -> Dict[str, Any]:
    """Scan git repository history and return repository bloat timeline data.

    Args:
        repo_path: Path to target git repository.
        revision: Target git branch/revision.
        max_commits: Limit of commits to analyze.
        threshold_mb: File size threshold in megabytes.
        top_n: Top N offending commits to highlight.

    Returns:
        Dictionary containing bloat timeline analysis results.
    """
    git_runner = GitRunner(repo_path)
    threshold_bytes = int(threshold_mb * 1024 * 1024)

    raw_commits = parse_commit_log(git_runner, revision, max_commits)
    bloat_commits: List[BloatCommit] = []

    for item in raw_commits:
        chash = item["hash"]
        net_bytes, large_files = analyze_commit_bloat(
            git_runner, chash, threshold_bytes
        )

        if net_bytes > threshold_bytes or large_files:
            bloat_commits.append(
                BloatCommit(
                    commit_hash=chash,
                    author=item["author"],
                    date=item["date"],
                    subject=item["subject"],
                    net_bytes_added=net_bytes,
                    large_files=large_files,
                )
            )

    # Sort commits by net_bytes_added descending
    sorted_commits = sorted(
        bloat_commits, key=lambda c: c.net_bytes_added, reverse=True
    )
    top_commits = sorted_commits[:top_n]

    return {
        "repository": os.path.abspath(repo_path),
        "commits_scanned": len(raw_commits),
        "bloat_commits_found": len(bloat_commits),
        "threshold_mb": threshold_mb,
        "timeline": [asdict(c) for c in bloat_commits],
        "top_bloat_commits": [asdict(c) for c in top_commits],
    }


def render_text_report(report: Dict[str, Any]) -> str:
    """Format analysis report dictionary as readable text output.

    Args:
        report: Dictionary containing report data.

    Returns:
        Formatted string for terminal display.
    """
    lines = [
        "=== Repo Bloat Timeline Report ===",
        f"Repository: {report['repository']}",
        f"Commits Scanned: {report['commits_scanned']}",
        f"Bloat Commits Found: {report['bloat_commits_found']}",
        f"Size Threshold: {report['threshold_mb']} MB",
        "",
        "--- Top Offending Commits ---",
    ]

    top_commits = report.get("top_bloat_commits", [])
    if not top_commits:
        lines.append("No commits exceeded the bloat threshold.")
    else:
        for idx, commit in enumerate(top_commits, 1):
            mb_added = commit["net_bytes_added"] / (1024 * 1024)
            lines.append(
                f"{idx}. [{commit['commit_hash'][:8]}] {commit['date'][:10]} "
                f"by {commit['author']} (+{mb_added:.2f} MB)"
            )
            lines.append(f"   Message: {commit['subject']}")
            if commit["large_files"]:
                lines.append("   Large Files:")
                for lf in commit["large_files"]:
                    file_mb = lf["size_bytes"] / (1024 * 1024)
                    lines.append(
                        f"     - {lf['path']} ({file_mb:.2f} MB, {lf['action']})"
                    )

    return "\n".join(lines)


def setup_cli() -> argparse.ArgumentParser:
    """Configure command line arguments parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Pinpoint when a Git repo grew in size and which "
            "commits/files caused it."
        )
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to Git repository root (default: current directory).",
    )
    parser.add_argument(
        "--branch",
        default="HEAD",
        help="Target Git revision/branch to analyze (default: HEAD).",
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=500,
        help="Maximum number of commits to scan (default: 500).",
    )
    parser.add_argument(
        "--threshold-mb",
        type=float,
        default=1.0,
        help="Bloat size threshold in megabytes (default: 1.0).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top offending commits to show (default: 10).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: text or json (default: text).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def main() -> None:
    """CLI entrypoint function for repo-bloat-timeline."""
    parser = setup_cli()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    try:
        results = find_repo_bloat_timeline(
            repo_path=args.repo,
            revision=args.branch,
            max_commits=args.max_commits,
            threshold_mb=args.threshold_mb,
            top_n=args.top,
        )

        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(render_text_report(results))

    except Exception as err:  # pylint: disable=broad-exception-caught
        logging.error("Failed to analyze repo bloat: %s", err)
        sys.exit(1)


if __name__ == "__main__":
    main()

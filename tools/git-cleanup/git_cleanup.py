#!/usr/bin/env python3
"""Git Repo Cleanup Tool.

Analyzes a git repository for:
- Large files (by size threshold)
- Stale branches (merged or inactive for N days)
- Untracked / gitignored junk files
- Accidentally committed secrets (entropy + regex)
"""

import argparse
import logging
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
# pylint: disable=too-many-locals,too-many-branches,too-many-statements
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_LARGE_FILE_KB: int = 500
DEFAULT_STALE_DAYS: int = 90
DEFAULT_ENTROPY_THRESHOLD: float = 4.5

# Secret patterns (value-only, not key names) — high-signal, low FP
SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "AWS Secret Key",
        re.compile(r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]"),
    ),
    (
        "Generic API Key",
        re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][0-9a-zA-Z\-_]{20,}['\"]"),
    ),
    ("Bearer Token", re.compile(r"Bearer\s+[A-Za-z0-9\-_]{20,}")),
    (
        "Private Key Header",
        re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    ),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("Generic Password", re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("Slack Token", re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}")),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("Stripe Key", re.compile(r"(?:r|s)k_(live|test)_[0-9a-zA-Z]{24,}")),
]

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class LargeFile:
    """A file exceeding the size threshold.

    Attributes:
        path: File path relative to repo root.
        size_bytes: File size in bytes.
    """

    path: str
    size_bytes: int

    @property
    def size_kb(self) -> float:
        """Return size in kilobytes."""
        return self.size_bytes / 1024


@dataclass
class StaleBranch:
    """A branch that is stale (merged or inactive).

    Attributes:
        name: Branch name.
        last_commit_date: ISO 8601 date of the last commit.
        days_since_commit: Days elapsed since last commit.
        is_merged: Whether the branch is merged into HEAD.
    """

    name: str
    last_commit_date: str
    days_since_commit: int
    is_merged: bool


@dataclass
class SecretFinding:
    """A potential secret found in a commit.

    Attributes:
        commit: Commit SHA.
        file_path: File containing the match.
        line_number: Approximate line number of the match.
        pattern_name: Human-readable name of the pattern that matched.
        snippet: Context snippet (value masked).
    """

    commit: str
    file_path: str
    line_number: int
    pattern_name: str
    snippet: str


@dataclass
class CleanupReport:
    """Full cleanup report for a repository.

    Attributes:
        repo_path: Absolute path to the repository.
        large_files: Files exceeding the size threshold.
        stale_branches: Stale local and remote branches.
        untracked_files: Files not tracked by git.
        ignored_junk: Files matched by .gitignore.
        secret_findings: Potential secrets found in git history.
    """

    repo_path: str
    large_files: List[LargeFile] = field(default_factory=list)
    stale_branches: List[StaleBranch] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)
    ignored_junk: List[str] = field(default_factory=list)
    secret_findings: List[SecretFinding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_git(
    args: List[str], cwd: str, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a git command and return the result.

    Args:
        args: git sub-command arguments.
        cwd: Working directory for the command.
        check: If True, raise CalledProcessError on non-zero exit.

    Returns:
        CompletedProcess instance.

    Raises:
        SystemExit: If the command fails and check is True.
    """
    cmd = ["git"] + args
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("git command failed: %s\n%s", " ".join(cmd), exc.stderr)
        sys.exit(1)
    except FileNotFoundError:
        logger.error("git not found on PATH.")
        sys.exit(1)


def shannon_entropy(data: str) -> float:
    """Calculate Shannon entropy of a string.

    Args:
        data: Input string.

    Returns:
        Entropy value in bits per character. Returns 0.0 for empty strings.
    """
    if not data:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in data:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def find_large_files(repo_path: str, threshold_kb: int) -> List[LargeFile]:
    """Find files in the git index exceeding a size threshold.

    Args:
        repo_path: Absolute path to the repository.
        threshold_kb: Size threshold in kilobytes.

    Returns:
        List of LargeFile objects sorted by size descending.
    """
    result = run_git(["ls-files", "-z"], repo_path)
    files = [f for f in result.stdout.split("\0") if f]
    large: List[LargeFile] = []
    for rel_path in files:
        abs_path = os.path.join(repo_path, rel_path)
        try:
            size = os.path.getsize(abs_path)
            if size >= threshold_kb * 1024:
                large.append(LargeFile(path=rel_path, size_bytes=size))
        except OSError:
            pass
    return sorted(large, key=lambda f: f.size_bytes, reverse=True)


def find_stale_branches(repo_path: str, stale_days: int) -> List[StaleBranch]:
    """Find stale local branches.

    A branch is stale if it was last committed to more than stale_days ago,
    or if it is already merged into the current HEAD.

    Args:
        repo_path: Absolute path to the repository.
        stale_days: Number of days threshold for staleness.

    Returns:
        List of StaleBranch objects.
    """
    # Get merged branches
    merged_result = run_git(
        ["branch", "--merged", "HEAD", "--format=%(refname:short)"],
        repo_path,
        check=False,
    )
    merged_names = set(merged_result.stdout.strip().splitlines())

    # Get all local branches with their last commit date
    all_result = run_git(
        ["branch", "--format=%(refname:short)%09%(committerdate:iso8601)"],
        repo_path,
        check=False,
    )

    stale: List[StaleBranch] = []
    now = datetime.now(tz=timezone.utc)

    for line in all_result.stdout.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        branch_name, date_str = parts[0].strip(), parts[1].strip()
        if branch_name in ("HEAD", "main", "master"):
            continue
        try:
            last_commit = datetime.fromisoformat(date_str)
            if last_commit.tzinfo is None:
                last_commit = last_commit.replace(tzinfo=timezone.utc)
            days_old = (now - last_commit).days
        except ValueError:
            days_old = -1
            last_commit = now

        is_merged = branch_name in merged_names
        if is_merged or days_old >= stale_days:
            stale.append(
                StaleBranch(
                    name=branch_name,
                    last_commit_date=date_str,
                    days_since_commit=days_old,
                    is_merged=is_merged,
                )
            )

    return sorted(stale, key=lambda b: b.days_since_commit, reverse=True)


def find_untracked_and_ignored(repo_path: str) -> Tuple[List[str], List[str]]:
    """Find untracked and gitignored files.

    Args:
        repo_path: Absolute path to the repository.

    Returns:
        Tuple of (untracked_files, ignored_files).
    """
    # Untracked (not staged, not ignored)
    untracked_result = run_git(
        ["ls-files", "--others", "--exclude-standard"], repo_path, check=False
    )
    untracked = [f for f in untracked_result.stdout.strip().splitlines() if f]

    # Ignored files present on disk
    ignored_result = run_git(
        ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        repo_path,
        check=False,
    )
    ignored = [f for f in ignored_result.stdout.split("\0") if f]

    return untracked, ignored


def scan_commits_for_secrets(
    repo_path: str,
    max_commits: int,
    entropy_threshold: float,
) -> List[SecretFinding]:
    """Scan recent git commits for potential secrets.

    Uses both regex pattern matching and Shannon entropy analysis.

    Args:
        repo_path: Absolute path to the repository.
        max_commits: Maximum number of recent commits to scan.
        entropy_threshold: Minimum entropy to flag a token as suspicious.

    Returns:
        List of SecretFinding objects (deduplicated by pattern+file).
    """
    # Get list of commits
    log_result = run_git(
        ["log", "--pretty=format:%H", f"-n{max_commits}"], repo_path, check=False
    )
    commits = [c for c in log_result.stdout.strip().splitlines() if c]

    findings: List[SecretFinding] = []
    seen_keys: set = set()  # (pattern_name, file_path) to deduplicate

    for commit in commits:
        diff_result = run_git(
            ["show", "--unified=0", "--no-color", commit], repo_path, check=False
        )
        current_file = ""
        line_num = 0

        for line in diff_result.stdout.splitlines():
            # Track current file
            if line.startswith("+++ b/"):
                current_file = line[6:]
                line_num = 0
                continue
            if line.startswith("@@ "):
                # @@ -a,b +c,d @@
                match = re.search(r"\+(\d+)", line)
                if match:
                    line_num = int(match.group(1)) - 1
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue

            line_num += 1
            content = line[1:]  # strip leading '+'

            # Pattern matching
            for pattern_name, pattern in SECRET_PATTERNS:
                key = (pattern_name, current_file)
                if key in seen_keys:
                    continue
                if pattern.search(content):
                    # Mask the matched value
                    masked = re.sub(
                        pattern, lambda m: m.group(0)[:4] + "***REDACTED***", content
                    )
                    findings.append(
                        SecretFinding(
                            commit=commit[:8],
                            file_path=current_file,
                            line_number=line_num,
                            pattern_name=pattern_name,
                            snippet=masked.strip()[:120],
                        )
                    )
                    seen_keys.add(key)

            # Entropy-based detection for high-entropy tokens
            tokens = re.findall(r"[A-Za-z0-9+/=_\-]{20,}", content)
            for token in tokens:
                entropy = shannon_entropy(token)
                if entropy >= entropy_threshold:
                    key = ("High-Entropy Token", current_file)
                    if key not in seen_keys:
                        findings.append(
                            SecretFinding(
                                commit=commit[:8],
                                file_path=current_file,
                                line_number=line_num,
                                pattern_name="High-Entropy Token",
                                snippet=(
                                    f"token={token[:6]}***REDACTED*** "
                                    f"(entropy={entropy:.2f})"
                                ),
                            )
                        )
                        seen_keys.add(key)

    return findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(report: CleanupReport, args: argparse.Namespace) -> None:
    """Print a formatted cleanup report to stdout.

    Args:
        report: The CleanupReport to display.
        args: Parsed CLI arguments (used for threshold context).
    """
    print(f"\n{'=' * 60}")
    print("  Git Repo Cleanup Report")
    print(f"  Repository: {report.repo_path}")
    print(f"{'=' * 60}\n")

    # Large files
    print(f"── Large Files (>{args.large_file_kb} KB) ──────────────────────────")
    if report.large_files:
        for lf in report.large_files:
            print(f"  {lf.size_kb:>8.1f} KB  {lf.path}")
    else:
        print("  ✅ No large tracked files found.")
    print()

    # Stale branches
    print(f"── Stale Branches (>{args.stale_days} days or merged) ────────────")
    if report.stale_branches:
        for b in report.stale_branches:
            flags = []
            if b.is_merged:
                flags.append("MERGED")
            if b.days_since_commit >= args.stale_days:
                flags.append(f"{b.days_since_commit}d old")
            flag_str = ", ".join(flags)
            print(f"  {b.name:<40} [{flag_str}]")
    else:
        print("  ✅ No stale branches found.")
    print()

    # Untracked files
    print("── Untracked Files ──────────────────────────────────────")
    if report.untracked_files:
        for f in report.untracked_files[:50]:
            print(f"  {f}")
        if len(report.untracked_files) > 50:
            print(f"  … and {len(report.untracked_files) - 50} more")
    else:
        print("  ✅ No untracked files.")
    print()

    # Ignored junk
    print("── Gitignored Files on Disk ──────────────────────────────")
    if report.ignored_junk:
        for f in report.ignored_junk[:50]:
            print(f"  {f}")
        if len(report.ignored_junk) > 50:
            print(f"  … and {len(report.ignored_junk) - 50} more")
    else:
        print("  ✅ No ignored files on disk.")
    print()

    # Secrets
    print("── Potential Secrets in Git History ─────────────────────")
    if report.secret_findings:
        for s in report.secret_findings:
            print(
                f"  ⚠ [{s.pattern_name}] commit={s.commit} "
                f"file={s.file_path}:{s.line_number}"
            )
            print(f"      {s.snippet}")
    else:
        print("  ✅ No obvious secrets detected.")
    print()
    print(f"{'=' * 60}")
    print("  Summary:")
    print(f"    Large files        : {len(report.large_files)}")
    print(f"    Stale branches     : {len(report.stale_branches)}")
    print(f"    Untracked files    : {len(report.untracked_files)}")
    print(f"    Ignored junk files : {len(report.ignored_junk)}")
    print(f"    Secret findings    : {len(report.secret_findings)}")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Git Repo Cleanup Tool — find bloat, stale branches, "
            "junk, and secrets."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python git_cleanup.py
  python git_cleanup.py --repo /path/to/repo --large-file-kb 1000
  python git_cleanup.py --stale-days 60 --max-commits 100
""",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the git repository (default: current directory).",
    )
    parser.add_argument(
        "--large-file-kb",
        type=int,
        default=DEFAULT_LARGE_FILE_KB,
        metavar="KB",
        help=(
            "Flag files larger than this size in KB "
            f"(default: {DEFAULT_LARGE_FILE_KB})."
        ),
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=DEFAULT_STALE_DAYS,
        metavar="DAYS",
        help=(
            "Flag branches inactive for this many days "
            f"(default: {DEFAULT_STALE_DAYS})."
        ),
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=50,
        metavar="N",
        help="Number of recent commits to scan for secrets (default: 50).",
    )
    parser.add_argument(
        "--entropy-threshold",
        type=float,
        default=DEFAULT_ENTROPY_THRESHOLD,
        metavar="FLOAT",
        help=(
            "Shannon entropy threshold for secret detection "
            f"(default: {DEFAULT_ENTROPY_THRESHOLD})."
        ),
    )
    parser.add_argument(
        "--skip-secrets",
        action="store_true",
        help="Skip the secret scanning step (faster).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        logger.error("'%s' does not appear to be a git repository.", repo_path)
        sys.exit(1)

    report = CleanupReport(repo_path=repo_path)

    logger.info("Scanning large files…")
    report.large_files = find_large_files(repo_path, args.large_file_kb)

    logger.info("Scanning stale branches…")
    report.stale_branches = find_stale_branches(repo_path, args.stale_days)

    logger.info("Scanning untracked/ignored files…")
    report.untracked_files, report.ignored_junk = find_untracked_and_ignored(repo_path)

    if not args.skip_secrets:
        logger.info("Scanning commits for secrets (this may take a moment)…")
        report.secret_findings = scan_commits_for_secrets(
            repo_path, args.max_commits, args.entropy_threshold
        )

    print_report(report, args)


if __name__ == "__main__":
    main()

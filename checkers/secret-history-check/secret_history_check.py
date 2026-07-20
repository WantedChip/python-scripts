#!/usr/bin/env python3
"""Secret History Check.

Audits Git repository commit logs and diff lines to verify if deleted secrets
(or active patterns) still reside in git history databases.
"""

import argparse
import os
import re
import subprocess  # nosec B404
import sys
from typing import Dict, List, Optional


def is_git_repo(repo_path: str) -> bool:
    """Verify if target folder is a Git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        return res.returncode == 0
    except OSError:
        return False


# pylint: disable=too-many-locals
def scan_git_history(repo_path: str, query: Optional[str]) -> List[Dict[str, str]]:
    """Scan all commits/diffs in the Git repository for secrets."""
    findings: List[Dict[str, str]] = []

    # Define regexes for common secrets
    rules = {
        "AWS Access Key ID": r"\bAKIA[0-9A-Z]{16}\b",
        "Generic Secret/Password Key": (
            r"(?i)(private_key|api_key|token|password|secret|passwd)\s*[:=]\s*"
            r"['\"][a-zA-Z0-9._~+/-]{16,}['\"]"
        ),
        "Private Key Header": r"-----BEGIN [A-Z ]+ PRIVATE KEY-----",
        "GitHub Token": r"\bgh[oprs]_[a-zA-Z0-9]{36,255}\b",
    }

    if query:
        # Override rules with user search query
        rules = {f"Search Query '{query}'": re.escape(query)}

    # Compile regexes
    compiled_rules = {name: re.compile(pat) for name, pat in rules.items()}

    # Run git log with patches (-p) across all branches (--all)
    cmd = ["git", "log", "-p", "--all", "--unified=0"]

    try:
        with subprocess.Popen(  # nosec B603
            cmd,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
        ) as proc:
            commit_hash = "Unknown"
            author = "Unknown"
            date_str = "Unknown"
            current_file = "Unknown"

            if proc.stdout is None:
                return findings

            for line in proc.stdout:
                line_strip = line.strip()

                # Track commit context
                if line_strip.startswith("commit "):
                    commit_hash = line_strip.split()[1]
                elif line_strip.startswith("Author: "):
                    author = line_strip[8:]
                elif line_strip.startswith("Date:   "):
                    date_str = line_strip[8:]
                elif line_strip.startswith("diff --git "):
                    parts = line_strip.split()
                    if len(parts) >= 4:
                        current_file = parts[3].lstrip("b/")

                # Parse only additions in the diff
                elif line.startswith("+") and not line.startswith("+++"):
                    added_content = line[1:]
                    for rule_name, rx in compiled_rules.items():
                        match = rx.search(added_content)
                        if match:
                            findings.append(
                                {
                                    "commit": commit_hash,
                                    "author": author,
                                    "date": date_str,
                                    "file": current_file,
                                    "leak_type": rule_name,
                                    "line": added_content.strip()[:80],
                                }
                            )
                            break
    except (OSError, ValueError, RuntimeError) as e:
        print(f"Error starting git log command: {e}", file=sys.stderr)
        return findings

    return findings


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Verify if secrets reside in Git commit history."
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Git repository folder path to audit (default: current directory).",
    )
    parser.add_argument(
        "-q",
        "--query",
        help="Specific secret string or keyword to search in historical diffs.",
    )

    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.exists(repo_path):
        print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
        sys.exit(1)

    # Check Git environment
    if not is_git_repo(repo_path):
        print(
            f"Error: '{repo_path}' is not inside a Git repository (or 'git' CLI "
            "is not installed).",
            file=sys.stderr,
        )
        sys.exit(1)

    print("========================================================================")
    print("SECRET HISTORY CHECK: GIT LOG LINTER")
    print("========================================================================")
    print(f"Auditing repository: {repo_path}")
    if args.query:
        print(f"Scanning history for occurrences of custom query: '{args.query}'")
    else:
        print(
            "Scanning history for common API keys, private key headers, and tokens..."
        )
    print("-" * 80)

    findings = scan_git_history(repo_path, args.query)

    if not findings:
        print(
            "\n[+] Success: No historical secrets or matches detected in Git diff "
            "history."
        )
        sys.exit(0)

    print(f"\n[!] WARNING: Flagged {len(findings)} secret matches in Git history:")
    print("=" * 80)

    # De-duplicate matches slightly to print clearly
    printed_commits = set()
    for f in findings:
        key = (f["commit"], f["file"], f["leak_type"])
        if key in printed_commits:
            continue
        printed_commits.add(key)

        author_str = f["author"].strip()
        date_val = f["date"].strip()
        print(f"Leak Type:  {f['leak_type']}")
        print(
            f"Commit:     {f['commit'][:10]} (Author: {author_str} | Date: {date_val})"
        )
        print(f"File:       {f['file']}")
        print(f"Match line: {f['line']}")
        print("-" * 80)

    print("\n" + "=" * 80)
    print("REMEDIATION ACTIONS:")
    print(
        "  These secrets are still stored in the Git history database and can "
        "be recovered."
    )
    print(
        "  To scrub them completely, use tools like git-filter-repo or "
        "BFG Repo-Cleaner:"
    )
    print("    git filter-repo --invert-paths --path <file_path>")
    print("  IMPORTANT: You must rotate any compromised keys immediately!")
    print("=" * 80)


if __name__ == "__main__":
    main()

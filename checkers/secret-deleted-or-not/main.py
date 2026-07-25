#!/usr/bin/env python3
"""Secret History Audit Tool.

Searches Git history, branches, stashes, reflogs, and commit objects
to verify if a leaked secret or key still exists in any historical Git ref.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals

import argparse
import json
import re
import subprocess  # nosec B404
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple


@dataclass
class Finding:
    """Class representing a found secret occurrence in Git history."""

    location_type: str  # 'commit', 'stash', 'reflog', 'uncommitted'
    identifier: str  # Commit hash or stash ref
    date: str
    author: str
    ref: str
    file_path: str
    snippet: str


class SecretHistoryChecker:
    """Audits Git repository history for occurrences of secrets."""

    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir.resolve()
        if not (self.repo_dir / ".git").exists() and not self._is_git_repo():
            err = f"Directory '{self.repo_dir}' is not a valid Git repository."
            raise ValueError(err)

    def _is_git_repo(self) -> bool:
        cmd = ["git", "rev-parse", "--is-inside-work-tree"]
        res = self._run_git(cmd)
        return res.strip() == "true"

    def _run_git(self, cmd: List[str]) -> str:
        try:
            result = subprocess.run(  # nosec B603 B607
                cmd,
                cwd=str(self.repo_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            return str(result.stdout)
        except subprocess.CalledProcessError as e:
            # Command returned non-zero (might mean no matches found in git grep)
            return str(e.stdout or "")

    def search_git_log_pickaxe(
        self, secret: str, is_regex: bool = False
    ) -> List[Finding]:
        """Search commits using git log -S or git log -G."""
        findings: List[Finding] = []
        flag = "-G" if is_regex else "-S"
        # Format: Commit Hash|Date|Author|Ref Names
        format_str = "%H|%ai|%an|%d"
        cmd = [
            "git",
            "log",
            "--all",
            "--full-history",
            flag,
            secret,
            f"--format=format:{format_str}",
            "--name-only",
        ]

        raw_output = self._run_git(cmd)
        if not raw_output.strip():
            return findings

        current_meta: Optional[Tuple[str, str, str, str]] = None
        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line and len(line.split("|")) >= 3:
                parts = line.split("|")
                commit_hash = parts[0]
                date = parts[1]
                author = parts[2]
                ref = parts[3] if len(parts) > 3 else ""
                current_meta = (commit_hash, date, author, ref)
            elif current_meta is not None:
                commit_hash, date, author, ref = current_meta
                file_path = line
                findings.append(
                    Finding(
                        location_type="commit",
                        identifier=commit_hash[:10],
                        date=date,
                        author=author,
                        ref=ref.strip(" ()"),
                        file_path=file_path,
                        snippet=f"Match found via pickaxe ({flag})",
                    )
                )

        return findings

    def search_stashes(self, secret: str, is_regex: bool = False) -> List[Finding]:
        """Search Git stash history for secret."""
        findings: List[Finding] = []
        stash_list_raw = self._run_git(["git", "stash", "list"])
        if not stash_list_raw.strip():
            return findings

        for line in stash_list_raw.splitlines():
            match = re.match(r"^(stash@\{\d+\}): (.*)$", line)
            if not match:
                continue
            stash_ref, description = match.groups()
            diff_cmd = ["git", "stash", "show", "-p", stash_ref]
            diff_output = self._run_git(diff_cmd)

            if is_regex:
                has_match = bool(re.search(secret, diff_output))
            else:
                has_match = secret in diff_output

            if has_match:
                findings.append(
                    Finding(
                        location_type="stash",
                        identifier=stash_ref,
                        date="Stashed state",
                        author="Local User",
                        ref=description,
                        file_path="Stashed changes",
                        snippet=f"Secret present in {stash_ref}",
                    )
                )

        return findings

    def search_reflog(self, secret: str, is_regex: bool = False) -> List[Finding]:
        """Search Git reflogs for secret."""
        findings: List[Finding] = []
        format_str = "%gD|%h|%gs"
        reflog_raw = self._run_git(["git", "reflog", f"--format={format_str}"])
        if not reflog_raw.strip():
            return findings

        seen_commits: Set[str] = set()
        for line in reflog_raw.splitlines():
            parts = line.split("|")
            if len(parts) >= 3:
                reflog_id, commit_hash, subject = parts[0], parts[1], parts[2]
                if commit_hash in seen_commits:
                    continue
                seen_commits.add(commit_hash)

                show_output = self._run_git(["git", "show", commit_hash])
                if is_regex:
                    has_match = bool(re.search(secret, show_output))
                else:
                    has_match = secret in show_output

                if has_match:
                    findings.append(
                        Finding(
                            location_type="reflog",
                            identifier=commit_hash,
                            date="Reflog entry",
                            author="Unknown",
                            ref=reflog_id,
                            file_path="Commit diff",
                            snippet=subject,
                        )
                    )

        return findings

    def audit_all(self, secret: str, is_regex: bool = False) -> List[Finding]:
        """Run secret check across commits, stashes, and reflogs."""
        all_findings: List[Finding] = []
        all_findings.extend(self.search_git_log_pickaxe(secret, is_regex))
        all_findings.extend(self.search_stashes(secret, is_regex))
        all_findings.extend(self.search_reflog(secret, is_regex))

        # Deduplicate findings by identifier + file_path
        unique_findings = []
        seen = set()
        for f in all_findings:
            key = (f.identifier, f.file_path, f.location_type)
            if key not in seen:
                seen.add(key)
                unique_findings.append(f)

        return unique_findings


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = "Audit Git history to verify if a deleted secret still exists."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-s",
        "--secret",
        required=True,
        help="Target key, token, or secret string to locate",
    )
    parser.add_argument(
        "-r",
        "--repo",
        type=Path,
        default=Path("."),
        help="Path to Git repository",
    )
    parser.add_argument(
        "-e",
        "--regex",
        action="store_true",
        help="Treat target secret as a regular expression",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output findings in JSON format"
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for secret-deleted-or-not."""
    parsed = parse_args(args)

    try:
        checker = SecretHistoryChecker(parsed.repo)
        findings = checker.audit_all(parsed.secret, parsed.regex)

        if parsed.json:
            print(json.dumps([asdict(f) for f in findings], indent=2))
        else:
            print(f"=== Secret Audit Results for: '{parsed.secret}' ===")
            if not findings:
                msg_ok = (
                    "SUCCESS: Secret was NOT found in any commit history, "
                    "stashes, or reflogs!"
                )
                print(msg_ok)
            else:
                msg_warn = (
                    f"WARNING: Secret still exists in {len(findings)} "
                    "Git locations!\n"
                )
                print(msg_warn)
                for i, f in enumerate(findings, 1):
                    print(f"[{i}] Location: {f.location_type.upper()}")
                    print(f"    Identifier: {f.identifier}")
                    print(f"    Date:       {f.date}")
                    print(f"    Author:     {f.author}")
                    print(f"    Ref:        {f.ref or 'N/A'}")
                    print(f"    File:       {f.file_path}")
                    print(f"    Snippet:    {f.snippet}")
                    print("-" * 50)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Intent Expiry Checker.

Audits TODO/FIXME/HACK comments in codebase against Git history and referenced
symbols to determine if their original intent has expired or been completed.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-few-public-methods,too-many-instance-attributes
# pylint: disable=too-many-nested-blocks

import argparse
import os
import re
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple


@dataclass
class TodoItem:
    """Represents a TODO/FIXME/HACK comment."""

    file_path: str
    line_number: int
    tag: str  # TODO, FIXME, HACK
    comment_text: str
    referenced_symbols: List[str]
    author: str = "Unknown"
    date: str = "Unknown"
    commit: str = "Unknown"
    status: str = "ACTIVE"  # ACTIVE, COMPLETED, OBSOLETE
    reason: str = ""


class IntentAuditor:
    """Audits codebase comments against git history and symbol existence."""

    TAG_PATTERN = re.compile(r"\b(TODO|FIXME|HACK)\b:?\s*(.*)", re.IGNORECASE)
    SYMBOL_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]+\b")

    def __init__(self, repo_dir: str | Path, use_git: bool = True):
        self.repo_dir = Path(repo_dir).resolve()
        self.use_git = use_git
        self.all_symbols: Set[str] = set()

    def index_repo_symbols(self) -> None:
        """Scan python and code files in repo to collect defined symbols."""
        symbol_def_pattern = re.compile(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
        for root, _, files in os.walk(self.repo_dir):
            for file in files:
                if file.endswith((".py", ".js", ".ts", ".java", ".c", ".cpp")):
                    fp = Path(root) / file
                    try:
                        text = fp.read_text(encoding="utf-8", errors="ignore")
                        for line in text.splitlines():
                            match = symbol_def_pattern.search(line)
                            if match:
                                self.all_symbols.add(match.group(1))
                    except (OSError, UnicodeDecodeError):
                        pass

    def get_git_blame_info(
        self, file_path: str, line_number: int
    ) -> Tuple[str, str, str]:
        """Fetch author, date, commit from git blame."""
        if not self.use_git:
            return "Unknown", "Unknown", "Unknown"

        try:
            cmd = [
                "git",
                "blame",
                "-L",
                f"{line_number},{line_number}",
                "--porcelain",
                file_path,
            ]
            res = subprocess.run(  # nosec B603 B607
                cmd,
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            author, date, commit = "Unknown", "Unknown", "Unknown"
            lines = res.stdout.splitlines()
            if lines:
                commit = lines[0].split()[0]
                for line in lines:
                    if line.startswith("author "):
                        author = line[7:].strip()
                    elif line.startswith("author-time "):
                        date = line[12:].strip()
            return author, date, commit
        except (OSError, subprocess.SubprocessError):
            return "Unknown", "Unknown", "Unknown"

    def audit(self) -> List[TodoItem]:
        """Scan codebase and classify TODO items."""
        self.index_repo_symbols()
        todo_items: List[TodoItem] = []

        for root, _, files in os.walk(self.repo_dir):
            for file in files:
                if file.startswith(".") or file.endswith(
                    (".pyc", ".png", ".jpg", ".zip")
                ):
                    continue

                full_path = Path(root) / file
                rel_path = full_path.relative_to(self.repo_dir).as_posix()

                try:
                    lines = full_path.read_text(
                        encoding="utf-8", errors="ignore"
                    ).splitlines()
                except (OSError, UnicodeDecodeError):
                    continue

                for line_idx, line_content in enumerate(lines, start=1):
                    match = self.TAG_PATTERN.search(line_content)
                    if not match:
                        continue

                    tag = match.group(1).upper()
                    text = match.group(2).strip()

                    ref_symbols = self.SYMBOL_PATTERN.findall(text)
                    author, date, commit = self.get_git_blame_info(rel_path, line_idx)

                    item = TodoItem(
                        file_path=rel_path,
                        line_number=line_idx,
                        tag=tag,
                        comment_text=text,
                        referenced_symbols=ref_symbols,
                        author=author,
                        date=date,
                        commit=commit,
                    )
                    self.classify_item(item)
                    todo_items.append(item)

        return todo_items

    def classify_item(self, item: TodoItem) -> None:
        """Classify a TODO item as OBSOLETE, COMPLETED, or ACTIVE."""
        lower_text = item.comment_text.lower()

        # Check for explicit completion keywords in text
        if "done" in lower_text or "fixed" in lower_text or "implemented" in lower_text:
            item.status = "COMPLETED"
            item.reason = "Comment text indicates item has been done/fixed."
            return

        # Check symbol references
        stop_words = {"TODO", "FIXME", "HACK", "FOR", "AND", "THE", "USE"}
        symbols = [
            s
            for s in item.referenced_symbols
            if len(s) > 2 and s.upper() not in stop_words
        ]
        if symbols:
            found_count = sum(1 for s in symbols if s in self.all_symbols)
            if found_count > 0:
                item.status = "COMPLETED"
                item.reason = f"Referenced symbol(s) {symbols} now exist in codebase."
                return
            if len(symbols) > 0 and not any(s in self.all_symbols for s in symbols):
                item.status = "OBSOLETE"
                item.reason = (
                    f"Referenced symbol(s) {symbols} no longer exist in codebase."
                )
                return

        item.status = "ACTIVE"
        item.reason = "Pending implementation."


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = "Audit TODO/FIXME/HACK comments against codebase intent expiry."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--path", required=True, help="Root directory of codebase to audit"
    )
    parser.add_argument(
        "--no-git", action="store_true", help="Disable git blame lookup"
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parsed = parse_args(args)

    auditor = IntentAuditor(repo_dir=parsed.path, use_git=not parsed.no_git)
    items = auditor.audit()

    print("=== Intent Expiry Audit Report ===")
    print(f"Codebase Path: {parsed.path}")
    print(f"Total Comments Found: {len(items)}\n")

    for item in items:
        print(f"[{item.status}] {item.tag} at {item.file_path}:{item.line_number}")
        print(f"  Comment: {item.comment_text}")
        print(f"  Author:  {item.author} ({item.date})")
        print(f"  Reason:  {item.reason}")
        print("-" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())

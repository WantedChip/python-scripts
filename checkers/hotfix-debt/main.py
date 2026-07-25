"""Hotfix Debt Checker.

Finds production hotfixes (deployed files / server copies) that were never
committed back to source control. Compares deployed directories against Git
source control, ignoring deployment artifacts & runtime logs.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-few-public-methods

import argparse
import difflib
import fnmatch
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

DEFAULT_IGNORES = [
    "*.log",
    "*.pyc",
    "__pycache__",
    ".git",
    ".gitignore",
    ".env",
    "*.tmp",
    "*.swp",
    "dist/*",
    "build/*",
    "node_modules/*",
    "*.tar.gz",
    "*.zip",
]


@dataclass
class FileDiffResult:
    """Represents the difference result for a single file."""

    relative_path: str
    status: str  # 'MODIFIED', 'DEPLOYED_ONLY', 'MISSING_IN_DEPLOYMENT'
    repo_content: str = ""
    deployed_content: str = ""
    patch: str = ""


@dataclass
class HotfixReport:
    """Report containing all detected hotfix differences."""

    repo_path: str
    deployed_path: str
    diffs: List[FileDiffResult] = field(default_factory=list)
    ignored_files: List[str] = field(default_factory=list)

    @property
    def has_hotfixes(self) -> bool:
        """Check if any hotfix diffs exist."""
        return len(self.diffs) > 0


class HotfixScanner:
    """Scans and compares deployed directory files against source repository."""

    def __init__(
        self,
        repo_dir: str | Path,
        deployed_dir: str | Path,
        ignore_patterns: Optional[List[str]] = None,
    ):
        self.repo_dir = Path(repo_dir).resolve()
        self.deployed_dir = Path(deployed_dir).resolve()
        self.ignore_patterns = (
            ignore_patterns if ignore_patterns is not None else DEFAULT_IGNORES
        )

    def is_ignored(self, rel_path: str) -> bool:
        """Check if a relative path matches any ignore pattern."""
        parts = Path(rel_path).parts
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(
                Path(rel_path).name, pattern
            ):
                return True
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
        return False

    def get_all_relative_files(self, base_dir: Path) -> Set[str]:
        """Get all relative file paths under base_dir excluding ignored files."""
        relative_paths: Set[str] = set()
        if not base_dir.exists():
            return relative_paths

        for root, _, files in os.walk(base_dir):
            for file in files:
                full_path = Path(root) / file
                rel = full_path.relative_to(base_dir).as_posix()
                if not self.is_ignored(rel):
                    relative_paths.add(rel)
        return relative_paths

    def scan(self) -> HotfixReport:
        """Perform scan comparing repo files with deployed files."""
        repo_files = self.get_all_relative_files(self.repo_dir)
        deployed_files = self.get_all_relative_files(self.deployed_dir)

        all_files = sorted(list(repo_files | deployed_files))
        report = HotfixReport(
            repo_path=str(self.repo_dir),
            deployed_path=str(self.deployed_dir),
        )

        for rel_path in all_files:
            repo_file_path = self.repo_dir / rel_path
            deployed_file_path = self.deployed_dir / rel_path

            if repo_file_path.exists() and deployed_file_path.exists():
                try:
                    repo_text = repo_file_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                    deployed_text = deployed_file_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                except (OSError, UnicodeDecodeError):
                    continue

                if repo_text != deployed_text:
                    patch = self.generate_file_patch(rel_path, repo_text, deployed_text)
                    report.diffs.append(
                        FileDiffResult(
                            relative_path=rel_path,
                            status="MODIFIED",
                            repo_content=repo_text,
                            deployed_content=deployed_text,
                            patch=patch,
                        )
                    )
            elif deployed_file_path.exists() and not repo_file_path.exists():
                try:
                    deployed_text = deployed_file_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                except (OSError, UnicodeDecodeError):
                    deployed_text = ""
                patch = self.generate_file_patch(rel_path, "", deployed_text)
                report.diffs.append(
                    FileDiffResult(
                        relative_path=rel_path,
                        status="DEPLOYED_ONLY",
                        repo_content="",
                        deployed_content=deployed_text,
                        patch=patch,
                    )
                )
            elif repo_file_path.exists() and not deployed_file_path.exists():
                try:
                    repo_text = repo_file_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                except (OSError, UnicodeDecodeError):
                    repo_text = ""
                patch = self.generate_file_patch(rel_path, repo_text, "")
                report.diffs.append(
                    FileDiffResult(
                        relative_path=rel_path,
                        status="MISSING_IN_DEPLOYMENT",
                        repo_content=repo_text,
                        deployed_content="",
                        patch=patch,
                    )
                )

        return report

    def generate_file_patch(
        self, rel_path: str, repo_content: str, deployed_content: str
    ) -> str:
        """Generate unified diff string between repo content and deployed content."""
        repo_lines = repo_content.splitlines(keepends=True)
        deployed_lines = deployed_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            repo_lines,
            deployed_lines,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
        return "".join(diff)


def create_patch_file(report: HotfixReport, output_file: Path) -> None:
    """Write unified patch of all hotfixes to output file."""
    patch_lines: List[str] = []
    for diff_res in report.diffs:
        if diff_res.patch:
            patch_lines.append(diff_res.patch)
            if not diff_res.patch.endswith("\n"):
                patch_lines.append("\n")

    output_file.write_text("".join(patch_lines), encoding="utf-8")


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = (
        "Find uncommitted hotfixes in deployed directory compared "
        "to git source repo."
    )
    parser = argparse.ArgumentParser(description=desc)
    subparsers = parser.add_subparsers(dest="command", help="Sub-command to run")

    scan_parser = subparsers.add_parser("scan", help="Scan for uncommitted hotfixes")
    scan_parser.add_argument(
        "--repo", required=True, help="Path to git repository root"
    )
    scan_parser.add_argument(
        "--deployed", required=True, help="Path to deployed server directory"
    )
    scan_parser.add_argument(
        "--ignore", nargs="*", default=DEFAULT_IGNORES, help="Ignore patterns"
    )

    patch_parser = subparsers.add_parser(
        "patch", help="Generate patch file from hotfixes"
    )
    patch_parser.add_argument(
        "--repo", required=True, help="Path to git repository root"
    )
    patch_parser.add_argument(
        "--deployed", required=True, help="Path to deployed server directory"
    )
    patch_parser.add_argument("--output", required=True, help="Output patch file path")
    patch_parser.add_argument(
        "--ignore", nargs="*", default=DEFAULT_IGNORES, help="Ignore patterns"
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parsed = parse_args(args)

    if not parsed.command:
        return 1

    scanner = HotfixScanner(
        repo_dir=parsed.repo,
        deployed_dir=parsed.deployed,
        ignore_patterns=parsed.ignore,
    )
    report = scanner.scan()

    if parsed.command == "scan":
        print("=== Hotfix Debt Scan Report ===")
        print(f"Repo Dir:     {report.repo_path}")
        print(f"Deployed Dir: {report.deployed_path}\n")

        if not report.has_hotfixes:
            print("No hotfix debt detected! Deployed files match repository source.")
            return 0

        print(f"Found {len(report.diffs)} discrepancy file(s):\n")
        for d in report.diffs:
            print(f"  [{d.status}] {d.relative_path}")

        return 1

    if parsed.command == "patch":
        out_path = Path(parsed.output).resolve()
        create_patch_file(report, out_path)
        print(f"Generated patch for {len(report.diffs)} files at: {out_path}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

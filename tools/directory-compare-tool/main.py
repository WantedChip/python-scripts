"""Directory Compare Tool.

Compares two directory trees and reports missing files, extra files, and
modified files by file size, modification time (mtime), and SHA-256
content hashes.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class FileDiff:
    """Represents differences between two files."""

    rel_path: str
    size_a: Optional[int] = None
    size_b: Optional[int] = None
    mtime_a: Optional[float] = None
    mtime_b: Optional[float] = None
    hash_a: Optional[str] = None
    hash_b: Optional[str] = None
    reasons: List[str] = field(default_factory=list)


@dataclass
class ComparisonReport:
    """Encapsulates overall directory comparison results."""

    dir_a: str
    dir_b: str
    missing_in_b: List[str] = field(default_factory=list)
    extra_in_b: List[str] = field(default_factory=list)
    modified_files: List[FileDiff] = field(default_factory=list)
    identical_files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for JSON output."""
        return {
            "dir_a": self.dir_a,
            "dir_b": self.dir_b,
            "missing_in_b": self.missing_in_b,
            "extra_in_b": self.extra_in_b,
            "modified_files": [asdict(f) for f in self.modified_files],
            "identical_files": self.identical_files,
            "summary": {
                "total_missing": len(self.missing_in_b),
                "total_extra": len(self.extra_in_b),
                "total_modified": len(self.modified_files),
                "total_identical": len(self.identical_files),
            },
        }


class DirectoryComparator:
    """Engine for recursive directory comparison."""

    def __init__(
        self,
        includes: Optional[List[str]] = None,
        excludes: Optional[List[str]] = None,
        verify_hash: bool = True,
    ):
        """Initialize comparator.

        Args:
            includes: Optional list of fnmatch globs to include.
            excludes: Optional list of fnmatch globs to exclude.
            verify_hash: Whether to calculate SHA256 hashes for content check.
        """
        self.includes = includes or []
        self.excludes = excludes or []
        self.verify_hash = verify_hash

    @staticmethod
    def compute_sha256(file_path: pathlib.Path) -> str:
        """Compute SHA256 hash of file."""
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError:
            return ""

    def is_path_matching(self, rel_path: str) -> bool:
        """Check if path passes include and exclude filters."""
        path_str = rel_path.replace("\\", "/")

        if self.excludes:
            for pattern in self.excludes:
                if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(
                    os.path.basename(path_str), pattern
                ):
                    return False

        if self.includes:
            matched = False
            for pattern in self.includes:
                if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(
                    os.path.basename(path_str), pattern
                ):
                    matched = True
                    break
            if not matched:
                return False

        return True

    def scan_directory(self, root_dir: pathlib.Path) -> Dict[str, pathlib.Path]:
        """Recursively scan directory and return map of relative paths."""
        file_map: Dict[str, pathlib.Path] = {}
        for entry in root_dir.rglob("*"):
            if entry.is_file():
                rel = str(entry.relative_to(root_dir))
                if self.is_path_matching(rel):
                    file_map[rel] = entry
        return file_map

    def compare(self, dir_a: pathlib.Path, dir_b: pathlib.Path) -> ComparisonReport:
        """Compare directory trees dir_a and dir_b.

        Args:
            dir_a: Base source directory.
            dir_b: Target comparison directory.

        Returns:
            ComparisonReport object detailing diffs.
        """
        files_a = self.scan_directory(dir_a)
        files_b = self.scan_directory(dir_b)

        report = ComparisonReport(dir_a=str(dir_a), dir_b=str(dir_b))

        paths_a: Set[str] = set(files_a.keys())
        paths_b: Set[str] = set(files_b.keys())

        report.missing_in_b = sorted(list(paths_a - paths_b))
        report.extra_in_b = sorted(list(paths_b - paths_a))

        common_paths = sorted(list(paths_a & paths_b))

        for rel in common_paths:
            file_a = files_a[rel]
            file_b = files_b[rel]

            stat_a = file_a.stat()
            stat_b = file_b.stat()

            reasons = []
            if stat_a.st_size != stat_b.st_size:
                reasons.append("Size mismatch")

            # Check modification time (with 1-second precision tolerance)
            if abs(stat_a.st_mtime - stat_b.st_mtime) > 1.0:
                reasons.append("Mtime mismatch")

            hash_a, hash_b = None, None
            if self.verify_hash:
                hash_a = self.compute_sha256(file_a)
                hash_b = self.compute_sha256(file_b)
                if hash_a != hash_b:
                    reasons.append("Hash mismatch")

            if reasons:
                report.modified_files.append(
                    FileDiff(
                        rel_path=rel,
                        size_a=stat_a.st_size,
                        size_b=stat_b.st_size,
                        mtime_a=stat_a.st_mtime,
                        mtime_b=stat_b.st_mtime,
                        hash_a=hash_a,
                        hash_b=hash_b,
                        reasons=reasons,
                    )
                )
            else:
                report.identical_files.append(rel)

        return report


def print_cli_summary(report: ComparisonReport) -> None:
    """Print side-by-side CLI summary of comparison results."""
    print("=" * 80)
    print("DIRECTORY COMPARISON REPORT")
    print(f"Dir A (Base)  : {report.dir_a}")
    print(f"Dir B (Target): {report.dir_b}")
    print("=" * 80)

    summary = report.to_dict()["summary"]
    print(
        f"Summary: {summary['total_identical']} Identical | "
        f"{summary['total_modified']} Modified | "
        f"{summary['total_missing']} Missing in B | "
        f"{summary['total_extra']} Extra in B"
    )
    print("-" * 80)

    if report.missing_in_b:
        print("\n[MISSING IN DIR B]")
        for item in report.missing_in_b:
            print(f"  - {item}")

    if report.extra_in_b:
        print("\n[EXTRA IN DIR B]")
        for item in report.extra_in_b:
            print(f"  + {item}")

    if report.modified_files:
        print("\n[MODIFIED FILES]")
        print(f"{'Path':<40} | {'Reasons':<25} | {'Size A vs B'}")
        print("-" * 80)
        for diff in report.modified_files:
            reasons_str = ", ".join(diff.reasons)
            sizes_str = f"{diff.size_a} vs {diff.size_b}"
            print(f"{diff.rel_path:<40} | {reasons_str:<25} | {sizes_str}")
    print("=" * 80)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Compare two directory trees and report missing, extra, "
        + "and modified files."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("dir_a", type=pathlib.Path, help="Base directory (Dir A)")
    parser.add_argument("dir_b", type=pathlib.Path, help="Target directory (Dir B)")
    parser.add_argument(
        "--exclude",
        action="append",
        help="Glob pattern to exclude (can specify multiple)",
    )
    parser.add_argument(
        "--include",
        action="append",
        help="Glob pattern to include (can specify multiple)",
    )
    parser.add_argument(
        "--no-hash",
        action="store_true",
        help="Disable SHA256 content hash verification",
    )
    parser.add_argument(
        "--json-output",
        type=pathlib.Path,
        help="Path to save JSON format comparison report",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.dir_a.is_dir():
        err_msg = f"Error: Dir A non-existent or not directory: {parsed.dir_a}"
        print(err_msg, file=sys.stderr)
        return 1
    if not parsed.dir_b.is_dir():
        err_msg = f"Error: Dir B non-existent or not directory: {parsed.dir_b}"
        print(err_msg, file=sys.stderr)
        return 1

    comparator = DirectoryComparator(
        includes=parsed.include,
        excludes=parsed.exclude,
        verify_hash=not parsed.no_hash,
    )

    report = comparator.compare(parsed.dir_a, parsed.dir_b)
    print_cli_summary(report)

    if parsed.json_output:
        try:
            with open(parsed.json_output, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
            print(f"\nJSON report written to: {parsed.json_output}")
        except OSError as e:
            print(f"Failed to write JSON report: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

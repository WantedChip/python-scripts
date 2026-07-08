#!/usr/bin/env python3
"""Disk Space Investigator.

Recursively scans a directory to report what is consuming storage.
Highlights unusually large files and folders and exports a report.
"""

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_TOP_N: int = 20
DEFAULT_LARGE_FILE_MB: float = 100.0


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FileEntry:
    """A single file entry in the scan result.

    Attributes:
        path: Absolute file path.
        size_bytes: File size in bytes.
    """

    path: str
    size_bytes: int

    @property
    def size_mb(self) -> float:
        """Return size in megabytes."""
        return self.size_bytes / (1024 * 1024)


@dataclass
class DirectoryEntry:
    """A directory with its total recursive size.

    Attributes:
        path: Absolute directory path.
        total_bytes: Total recursive size in bytes.
        file_count: Total number of files under this directory.
    """

    path: str
    total_bytes: int
    file_count: int

    @property
    def total_mb(self) -> float:
        """Return size in megabytes."""
        return self.total_bytes / (1024 * 1024)


@dataclass
class ScanResult:
    """Full scan result for a directory.

    Attributes:
        root: Scanned root directory.
        total_bytes: Total size of all files.
        total_files: Total number of files scanned.
        top_files: Largest individual files.
        top_dirs: Largest sub-directories.
        large_files: Files exceeding the large-file threshold.
        extension_breakdown: Size by file extension.
    """

    root: str
    total_bytes: int = 0
    total_files: int = 0
    top_files: List[FileEntry] = field(default_factory=list)
    top_dirs: List[DirectoryEntry] = field(default_factory=list)
    large_files: List[FileEntry] = field(default_factory=list)
    extension_breakdown: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def human_readable(size_bytes: int) -> str:
    """Convert bytes to a human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Human-readable string (e.g., '1.23 GB').
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes //= 1024  # type: ignore[assignment]
    return f"{size_bytes:.2f} PB"


# pylint: disable=too-many-locals
def scan_directory(
    root: str,
    top_n: int,
    large_file_mb: float,
    exclude_dirs: Tuple[str, ...],
) -> ScanResult:
    """Recursively scan a directory and collect size statistics.

    Args:
        root: Root directory to scan.
        top_n: Number of top files/directories to track.
        large_file_mb: Threshold in MB for flagging large files.
        exclude_dirs: Directory names to skip.

    Returns:
        ScanResult with all collected data.
    """
    result = ScanResult(root=root)
    all_files: List[FileEntry] = []
    dir_sizes: Dict[str, int] = {}
    dir_file_counts: Dict[str, int] = {}
    ext_sizes: Dict[str, int] = {}
    large_threshold = int(large_file_mb * 1024 * 1024)

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Prune excluded directories
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        dir_bytes = 0
        for filename in filenames:
            fpath = os.path.join(dirpath, filename)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                logger.warning("Cannot stat '%s' — skipping.", fpath)
                continue

            result.total_bytes += size
            result.total_files += 1
            dir_bytes += size
            all_files.append(FileEntry(path=fpath, size_bytes=size))

            # Extension breakdown
            ext = os.path.splitext(filename)[1].lower() or "(no ext)"
            ext_sizes[ext] = ext_sizes.get(ext, 0) + size

        # Record directory size (add to all parent dirs)
        parts = Path(dirpath).parts
        for i in range(len(parts)):
            ancestor = str(Path(*parts[: i + 1]))
            dir_sizes[ancestor] = dir_sizes.get(ancestor, 0) + dir_bytes
            dir_file_counts[ancestor] = dir_file_counts.get(ancestor, 0) + len(
                filenames
            )

    # Top files by size
    all_files.sort(key=lambda f: f.size_bytes, reverse=True)
    result.top_files = all_files[:top_n]

    # Large files
    result.large_files = [f for f in all_files if f.size_bytes >= large_threshold]

    # Top directories (exclude the root itself, only report sub-dirs)
    root_abs = os.path.abspath(root)
    sub_dirs = [
        DirectoryEntry(
            path=path,
            total_bytes=size,
            file_count=dir_file_counts.get(path, 0),
        )
        for path, size in dir_sizes.items()
        if os.path.abspath(path) != root_abs
    ]
    sub_dirs.sort(key=lambda d: d.total_bytes, reverse=True)
    result.top_dirs = sub_dirs[:top_n]

    # Extension breakdown (sorted by size)
    result.extension_breakdown = dict(
        sorted(ext_sizes.items(), key=lambda kv: kv[1], reverse=True)
    )

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(result: ScanResult, args: argparse.Namespace) -> None:
    """Print a formatted disk usage report to stdout.

    Args:
        result: ScanResult to display.
        args: Parsed CLI args (for threshold context).
    """
    print(f"\n{'=' * 65}")
    print("  Disk Space Investigator")
    print(f"  Root      : {result.root}")
    print(
        f"  Total     : {human_readable(result.total_bytes)}  "
        f"({result.total_files:,} files)"
    )
    print(f"{'=' * 65}\n")

    print(
        f"── Top {len(result.top_files)} Largest Files "
        "─────────────────────────────────"
    )
    for f in result.top_files:
        rel = os.path.relpath(f.path, result.root)
        print(f"  {human_readable(f.size_bytes):>10}  {rel}")
    print()

    print(
        f"── Top {len(result.top_dirs)} Largest Sub-directories ──────────────────────"
    )
    for d in result.top_dirs:
        rel = os.path.relpath(d.path, result.root)
        print(f"  {human_readable(d.total_bytes):>10}  {rel}  ({d.file_count:,} files)")
    print()

    if result.large_files:
        print(
            f"── Files Exceeding {args.large_file_mb} MB ──────────────────────────────"
        )
        for f in result.large_files:
            rel = os.path.relpath(f.path, result.root)
            print(f"  ⚠  {human_readable(f.size_bytes):>10}  {rel}")
        print()

    print("── Space by Extension (Top 15) ───────────────────────────")
    for i, (ext, size) in enumerate(result.extension_breakdown.items()):
        if i >= 15:
            break
        pct = (size / result.total_bytes * 100) if result.total_bytes else 0
        print(f"  {ext:<15}  {human_readable(size):>10}  ({pct:.1f}%)")
    print()


def export_report(result: ScanResult, output_path: str, fmt: str) -> None:
    """Export the scan result to a file.

    Args:
        result: ScanResult to export.
        output_path: Destination file path.
        fmt: Export format — 'json', 'csv', or 'txt'.
    """
    if fmt == "json":
        data = {
            "root": result.root,
            "total_bytes": result.total_bytes,
            "total_files": result.total_files,
            "top_files": [
                {"path": f.path, "size_bytes": f.size_bytes} for f in result.top_files
            ],
            "top_dirs": [
                {
                    "path": d.path,
                    "total_bytes": d.total_bytes,
                    "file_count": d.file_count,
                }
                for d in result.top_dirs
            ],
            "large_files": [
                {"path": f.path, "size_bytes": f.size_bytes} for f in result.large_files
            ],
            "extension_breakdown": result.extension_breakdown,
        }
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    elif fmt == "csv":
        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["type", "path", "size_bytes", "size_human", "extra"])
            for f in result.top_files:
                writer.writerow(
                    ["file", f.path, f.size_bytes, human_readable(f.size_bytes), ""]
                )
            for d in result.top_dirs:
                writer.writerow(
                    [
                        "dir",
                        d.path,
                        d.total_bytes,
                        human_readable(d.total_bytes),
                        f"files={d.file_count}",
                    ]
                )

    elif fmt == "txt":
        lines = [
            f"Root: {result.root}",
            f"Total: {human_readable(result.total_bytes)} "
            f"({result.total_files:,} files)",
            "",
            "Top Files:",
        ]
        for f in result.top_files:
            lines.append(f"  {human_readable(f.size_bytes):>10}  {f.path}")
        lines += ["", "Top Directories:"]
        for d in result.top_dirs:
            lines.append(f"  {human_readable(d.total_bytes):>10}  {d.path}")
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

    logger.info("Report exported to %s", output_path)


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
        description="Disk Space Investigator — find what is eating your storage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python space_investigator.py
  python space_investigator.py --root /var/log --top 30
  python space_investigator.py --root ~/Downloads --output report.json --format json
  python space_investigator.py --large-file-mb 500 --exclude .git node_modules
""",
    )
    parser.add_argument(
        "--root",
        default=".",
        metavar="DIR",
        help="Directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP_N,
        metavar="N",
        help=f"Number of top files/dirs to show (default: {DEFAULT_TOP_N}).",
    )
    parser.add_argument(
        "--large-file-mb",
        type=float,
        default=DEFAULT_LARGE_FILE_MB,
        metavar="MB",
        help=(
            "Highlight files exceeding this size in MB "
            f"(default: {DEFAULT_LARGE_FILE_MB})."
        ),
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        default=[],
        metavar="DIR",
        help="Directory names to skip during scan.",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Export report to a file.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "txt"],
        default="json",
        help="Export format (default: json).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
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

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        logger.error("Directory not found: %s", root)
        sys.exit(1)

    logger.info("Scanning '%s'…", root)
    result = scan_directory(
        root=root,
        top_n=args.top,
        large_file_mb=args.large_file_mb,
        exclude_dirs=tuple(args.exclude),
    )

    print_report(result, args)

    if args.output:
        export_report(result, args.output, args.format)


if __name__ == "__main__":
    main()

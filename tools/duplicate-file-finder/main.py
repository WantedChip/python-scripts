#!/usr/bin/env python3
"""Duplicate File Finder CLI.

Features:
- Fast multi-stage detection:
  1. Size pre-filtering
  2. Partial head-hashing (4KB)
  3. Full chunked SHA-256 hashing
- Report generation: Console table, JSON, CSV
- Action modes: Dry-run, Quarantine, and Deletion
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class DuplicateGroup:
    """Class representing a group of duplicate files with a shared hash."""

    hash_val: str
    file_size: int
    files: List[Path]


def calculate_file_hash(
    filepath: Path,
    partial_bytes: Optional[int] = None,
    chunk_size: int = 65536,
) -> str:
    """Computes SHA-256 hash of a file.

    If partial_bytes is given, only reads the first N bytes.
    """
    hasher = hashlib.sha256()
    bytes_read = 0

    with open(filepath, "rb") as f:
        while True:
            read_len = chunk_size
            if partial_bytes is not None:
                read_len = min(chunk_size, partial_bytes - bytes_read)
                if read_len <= 0:
                    break

            chunk = f.read(read_len)
            if not chunk:
                break

            hasher.update(chunk)
            bytes_read += len(chunk)

    return hasher.hexdigest()


def find_duplicates(
    directory: Path,
    min_size: int = 1,
    exclude_patterns: Optional[List[str]] = None,
    chunk_size: int = 65536,
) -> List[DuplicateGroup]:
    """Scans directory recursively and finds identical files."""
    if not directory.exists() or not directory.is_dir():
        err_msg = f"Directory '{directory}' non-existent or not directory."
        raise ValueError(err_msg)

    exclude_set = set(exclude_patterns) if exclude_patterns else set()

    # Stage 1: Filter files by size
    size_groups: Dict[int, List[Path]] = defaultdict(list)

    for entry in directory.rglob("*"):
        if not entry.is_file():
            continue

        if any(pattern in entry.name for pattern in exclude_set):
            continue

        try:
            size = entry.stat().st_size
            if size >= min_size:
                size_groups[size].append(entry)
        except (PermissionError, FileNotFoundError):
            continue

    # Filter sizes with only 1 file
    cand_size_groups = {s: files for s, files in size_groups.items() if len(files) > 1}

    # Stage 2: Partial hash comparison (first 4KB)
    partial_groups: Dict[Tuple[int, str], List[Path]] = defaultdict(list)
    for size, files in cand_size_groups.items():
        for filepath in files:
            try:
                p_hash = calculate_file_hash(
                    filepath, partial_bytes=4096, chunk_size=chunk_size
                )
                partial_groups[(size, p_hash)].append(filepath)
            except (PermissionError, FileNotFoundError):
                continue

    cand_partial_groups = {
        key: files for key, files in partial_groups.items() if len(files) > 1
    }

    # Stage 3: Full SHA-256 hash comparison
    duplicate_groups: List[DuplicateGroup] = []

    for (size, _), files in cand_partial_groups.items():
        full_hash_groups: Dict[str, List[Path]] = defaultdict(list)
        for filepath in files:
            try:
                f_hash = calculate_file_hash(filepath, chunk_size=chunk_size)
                full_hash_groups[f_hash].append(filepath)
            except (PermissionError, FileNotFoundError):
                continue

        for f_hash, dups in full_hash_groups.items():
            if len(dups) > 1:
                # Sort paths deterministically
                dups.sort(key=lambda p: (len(str(p)), str(p)))
                group = DuplicateGroup(hash_val=f_hash, file_size=size, files=dups)
                duplicate_groups.append(group)

    duplicate_groups.sort(key=lambda g: g.file_size * (len(g.files) - 1), reverse=True)
    return duplicate_groups


def format_bytes(size: int) -> str:
    """Convert byte count to human-readable string."""
    float_size = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if float_size < 1024:
            return f"{float_size:.2f} {unit}" if unit != "B" else f"{size} B"
        float_size /= 1024.0
    return f"{float_size:.2f} PB"


def generate_console_report(duplicate_groups: List[DuplicateGroup]) -> str:
    """Generates human-readable console table report."""
    if not duplicate_groups:
        return "No duplicate files found."

    total_wasted = sum(g.file_size * (len(g.files) - 1) for g in duplicate_groups)
    total_files = sum(len(g.files) for g in duplicate_groups)

    lines = [
        "=== Duplicate File Finder Report ===",
        (
            f"Found {len(duplicate_groups)} duplicate group(s) containing "
            f"{total_files} files."
        ),
        f"Estimated space saveable: {format_bytes(total_wasted)}",
        "-" * 60,
    ]

    for idx, group in enumerate(duplicate_groups, start=1):
        wasted = group.file_size * (len(group.files) - 1)
        header_msg = (
            f"Group {idx} | Hash: {group.hash_val[:12]}... | "
            f"Size: {format_bytes(group.file_size)} | "
            f"Wasted: {format_bytes(wasted)}"
        )
        lines.append(header_msg)
        lines.append(f"  [Original]   : {group.files[0]}")
        for dup in group.files[1:]:
            lines.append(f"  [Duplicate]  : {dup}")
        lines.append("")

    return "\n".join(lines)


def export_json_report(
    duplicate_groups: List[DuplicateGroup], output_file: Path
) -> None:
    """Exports duplicate report to JSON file."""
    data = {
        "summary": {
            "group_count": len(duplicate_groups),
            "total_duplicate_files": sum(len(g.files) for g in duplicate_groups),
            "total_wasted_bytes": sum(
                g.file_size * (len(g.files) - 1) for g in duplicate_groups
            ),
        },
        "groups": [
            {
                "hash": g.hash_val,
                "file_size": g.file_size,
                "original": str(g.files[0]),
                "duplicates": [str(f) for f in g.files[1:]],
            }
            for g in duplicate_groups
        ],
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def export_csv_report(
    duplicate_groups: List[DuplicateGroup], output_file: Path
) -> None:
    """Exports duplicate report to CSV file."""
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["group_id", "hash", "file_size_bytes", "role", "file_path"])
        for idx, group in enumerate(duplicate_groups, start=1):
            writer.writerow(
                [
                    idx,
                    group.hash_val,
                    group.file_size,
                    "original",
                    str(group.files[0]),
                ]
            )
            for dup in group.files[1:]:
                writer.writerow(
                    [idx, group.hash_val, group.file_size, "duplicate", str(dup)]
                )


def process_quarantine(
    duplicate_groups: List[DuplicateGroup],
    quarantine_dir: Path,
    dry_run: bool = True,
) -> List[Tuple[Path, Path]]:
    """Moves duplicate files into quarantine directory."""
    actions: List[Tuple[Path, Path]] = []
    if not dry_run:
        quarantine_dir.mkdir(parents=True, exist_ok=True)

    for group in duplicate_groups:
        for dup_file in group.files[1:]:
            target_name = dup_file.name
            target_path = quarantine_dir / target_name

            # Collision prevention in quarantine folder
            counter = 1
            while target_path.exists() or any(tgt == target_path for _, tgt in actions):
                stem_sfx = f"{dup_file.stem}_{counter}{dup_file.suffix}"
                target_path = quarantine_dir / stem_sfx
                counter += 1

            actions.append((dup_file, target_path))
            if not dry_run:
                dup_file.rename(target_path)

    return actions


def process_deletion(
    duplicate_groups: List[DuplicateGroup], dry_run: bool = True
) -> List[Path]:
    """Deletes duplicate files (excluding the original in each group)."""
    deleted: List[Path] = []
    for group in duplicate_groups:
        for dup_file in group.files[1:]:
            deleted.append(dup_file)
            if not dry_run:
                dup_file.unlink()
    return deleted


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Find and manage duplicate files using SHA-256 hashing."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--dir",
        "-d",
        default=".",
        help="Target directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=1,
        help="Minimum file size in bytes (default: 1)",
    )
    parser.add_argument(
        "--exclude", nargs="*", help="Filename patterns or names to exclude"
    )
    parser.add_argument("--json", help="Export report to JSON file path")
    parser.add_argument("--csv", help="Export report to CSV file path")
    parser.add_argument(
        "--quarantine", help="Directory path to quarantine duplicate files"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete duplicate files (requires --apply)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply quarantine or deletion operations",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompt"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for duplicate file finder."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    target_dir = Path(parsed.dir)

    print(f"Scanning for duplicates in '{target_dir}'...")
    duplicate_groups = find_duplicates(
        directory=target_dir,
        min_size=parsed.min_size,
        exclude_patterns=parsed.exclude,
    )

    report = generate_console_report(duplicate_groups)
    print(report)

    if parsed.json:
        export_json_report(duplicate_groups, Path(parsed.json))
        print(f"Exported JSON report to '{parsed.json}'.")

    if parsed.csv:
        export_csv_report(duplicate_groups, Path(parsed.csv))
        print(f"Exported CSV report to '{parsed.csv}'.")

    if not duplicate_groups:
        return 0

    # Handle Actions (Quarantine / Delete)
    if parsed.quarantine:
        q_dir = Path(parsed.quarantine)
        if not parsed.apply:
            msg = (
                "\n[DRY RUN] Would move duplicate files to quarantine "
                + f"directory '{q_dir}'. Use --apply to execute."
            )
            print(msg)
        else:
            if not parsed.yes:
                confirm = input(f"Move duplicates to '{q_dir}'? [y/N]: ")
                if confirm.lower() != "y":
                    print("Quarantine operation cancelled.")
                    return 0
            moved = process_quarantine(duplicate_groups, q_dir, dry_run=False)
            print(f"Quarantined {len(moved)} duplicate file(s) into '{q_dir}'.")

    elif parsed.delete:
        if not parsed.apply:
            msg = (
                "\n[DRY RUN] Would delete duplicate files. " + "Use --apply to execute."
            )
            print(msg)
        else:
            if not parsed.yes:
                confirm = input("Permanently delete duplicate files? [y/N]: ")
                if confirm.lower() != "y":
                    print("Deletion operation cancelled.")
                    return 0
            deleted = process_deletion(duplicate_groups, dry_run=False)
            print(f"Permanently deleted {len(deleted)} duplicate file(s).")

    return 0


if __name__ == "__main__":
    sys.exit(main())

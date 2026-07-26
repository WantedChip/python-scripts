"""Folder Sync Tool.

Provides one-way and bidirectional folder synchronization with SHA256 checksum
verification, deletion tracking, conflict detection, and execution log export.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=too-many-nested-blocks

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        file_path: Path to file.

    Returns:
        Hexadecimal hash string.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def scan_tree(root_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Scan directory tree and return map of relative path strings to info.

    Returns:
        Dict mapping rel_path string to dict with 'size', 'mtime', 'full_path'.
    """
    result: Dict[str, Dict[str, Any]] = {}
    root_dir = Path(root_dir).resolve()
    if not root_dir.exists():
        return result

    for root, _, files in os.walk(root_dir):
        for f in files:
            full_path = Path(root) / f
            try:
                rel_path = full_path.relative_to(root_dir).as_posix()
                stat = full_path.stat()
                result[rel_path] = {
                    "size": float(stat.st_size),
                    "mtime": stat.st_mtime,
                    "full_path": full_path,
                }
            except (OSError, ValueError):
                pass
    return result


def are_files_identical(file1: Path, file2: Path, use_checksum: bool = True) -> bool:
    """Check if two files are identical based on size and mtime or SHA-256.

    Args:
        file1: Path to first file.
        file2: Path to second file.
        use_checksum: If True, compares SHA-256 hashes.

    Returns:
        True if files are determined to be identical.
    """
    s1, s2 = file1.stat(), file2.stat()
    if s1.st_size != s2.st_size:
        return False

    if use_checksum:
        return compute_sha256(file1) == compute_sha256(file2)

    return abs(s1.st_mtime - s2.st_mtime) < 1.0


def sync_folders(
    source_dir: Path,
    dest_dir: Path,
    direction: str = "one-way",
    delete: bool = False,
    use_checksum: bool = True,
    dry_run: bool = False,
) -> List[Dict[str, str]]:
    """Synchronize source and destination directories.

    Args:
        source_dir: Source root path.
        dest_dir: Destination root path.
        direction: 'one-way' or 'bidirectional'.
        delete: Delete extra files in destination (one-way mode).
        use_checksum: Use SHA-256 hash comparison.
        dry_run: Simulate operations without writing to disk.

    Returns:
        List of log records.
    """
    source_dir = Path(source_dir).resolve()
    dest_dir = Path(dest_dir).resolve()
    logs: List[Dict[str, str]] = []

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    source_tree = scan_tree(source_dir)
    dest_tree = scan_tree(dest_dir)

    all_rel_paths = set(source_tree.keys()).union(set(dest_tree.keys()))

    for rel_path in sorted(all_rel_paths):
        src_info = source_tree.get(rel_path)
        dst_info = dest_tree.get(rel_path)

        src_file = source_dir / rel_path
        dst_file = dest_dir / rel_path

        if direction == "one-way":
            if src_info and not dst_info:
                # Copy new file to dest
                record = {
                    "action": "copy_new",
                    "source": str(src_file),
                    "dest": str(dst_file),
                    "status": "success",
                }
                if not dry_run:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                logs.append(record)

            elif src_info and dst_info:
                # File exists in both
                if not are_files_identical(src_file, dst_file, use_checksum):
                    record = {
                        "action": "update",
                        "source": str(src_file),
                        "dest": str(dst_file),
                        "status": "success",
                    }
                    if not dry_run:
                        shutil.copy2(src_file, dst_file)
                    logs.append(record)

            elif not src_info and dst_info:
                # File present in dest, missing in source
                if delete:
                    record = {
                        "action": "delete",
                        "source": str(src_file),
                        "dest": str(dst_file),
                        "status": "success",
                    }
                    if not dry_run:
                        dst_file.unlink()
                    logs.append(record)

        elif direction == "bidirectional":
            if src_info and not dst_info:
                record = {
                    "action": "copy_to_dest",
                    "source": str(src_file),
                    "dest": str(dst_file),
                    "status": "success",
                }
                if not dry_run:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                logs.append(record)

            elif not src_info and dst_info:
                record = {
                    "action": "copy_to_source",
                    "source": str(dst_file),
                    "dest": str(src_file),
                    "status": "success",
                }
                if not dry_run:
                    src_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst_file, src_file)
                logs.append(record)

            elif src_info and dst_info:
                if not are_files_identical(src_file, dst_file, use_checksum):
                    # Conflict or update needed based on mtime
                    mtime_diff = src_info["mtime"] - dst_info["mtime"]
                    if abs(mtime_diff) < 1.0:
                        # Conflict! Content differs but mtime is identical
                        conflict_dst = dest_dir / f"{rel_path}.conflict"
                        record = {
                            "action": "conflict",
                            "source": str(src_file),
                            "dest": str(conflict_dst),
                            "status": "conflict_created",
                        }
                        if not dry_run:
                            shutil.copy2(src_file, conflict_dst)
                        logs.append(record)
                    elif mtime_diff > 0:
                        # Source is newer
                        record = {
                            "action": "update_dest",
                            "source": str(src_file),
                            "dest": str(dst_file),
                            "status": "success",
                        }
                        if not dry_run:
                            shutil.copy2(src_file, dst_file)
                        logs.append(record)
                    else:
                        # Dest is newer
                        record = {
                            "action": "update_source",
                            "source": str(dst_file),
                            "dest": str(src_file),
                            "status": "success",
                        }
                        if not dry_run:
                            shutil.copy2(dst_file, src_file)
                        logs.append(record)

    return logs


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Synchronize folders with checksums and delete tracking."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        type=Path,
        help="Source directory",
    )
    parser.add_argument(
        "--dest",
        "-d",
        required=True,
        type=Path,
        help="Destination directory",
    )
    parser.add_argument(
        "--direction",
        choices=["one-way", "bidirectional"],
        default="one-way",
        help="Sync direction",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete files in dest missing from source (one-way)",
    )
    parser.add_argument(
        "--checksum",
        action="store_true",
        default=True,
        help="Use SHA-256 checksum verification",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("sync_log.json"),
        help="Output log file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate sync without file modifications",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for folder-sync-tool."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    logs = sync_folders(
        source_dir=parsed.source,
        dest_dir=parsed.dest,
        direction=parsed.direction,
        delete=parsed.delete,
        use_checksum=parsed.checksum,
        dry_run=parsed.dry_run,
    )

    print(f"Sync complete. {len(logs)} actions executed/proposed.")
    if parsed.log_file:
        with open(parsed.log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
        print(f"Log saved to {parsed.log_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

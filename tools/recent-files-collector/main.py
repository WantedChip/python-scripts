"""Recent Files Collector.

Copies files modified or created within N days from a source directory tree
into a flat destination folder, handling filename collisions and writing a
manifest.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set


def get_file_timestamp(file_path: Path, time_type: str) -> float:
    """Retrieve mtime or ctime for a given file path.

    Args:
        file_path: Path to the file.
        time_type: 'mtime' for modification time, 'ctime' for creation/change.

    Returns:
        Timestamp as float (seconds since epoch).
    """
    stat = file_path.stat()
    if time_type == "ctime":
        return float(getattr(stat, "st_birthtime", stat.st_ctime))
    return float(stat.st_mtime)


def is_file_recent(
    file_path: Path,
    days: float,
    time_type: str = "mtime",
    now: Optional[datetime] = None,
) -> bool:
    """Check if a file was modified or created within the given number of days.

    Args:
        file_path: Path to the file.
        days: Maximum age of file in days.
        time_type: 'mtime' or 'ctime'.
        now: Optional datetime override for testing.

    Returns:
        True if the file timestamp is within the threshold.
    """
    ts = get_file_timestamp(file_path, time_type)
    file_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    current_dt = now or datetime.now(timezone.utc)
    threshold_dt = current_dt - timedelta(days=days)
    return file_dt >= threshold_dt


def generate_unique_filename(
    dest_dir: Path,
    original_name: str,
    used_names: Set[str],
    source_path: Path,
    strategy: str = "counter",
) -> str:
    """Generate a unique filename in destination directory for collisions.

    Args:
        dest_dir: Destination directory path.
        original_name: Base filename (e.g. 'doc.txt').
        used_names: Set of filenames already assigned in destination.
        source_path: Path of the source file (used for hashing).
        strategy: 'counter' (adds _1, _2) or 'hash' (adds MD5 hash).

    Returns:
        A unique filename string.
    """
    is_used = original_name in used_names
    exists = (dest_dir / original_name).exists()
    if not is_used and not exists:
        used_names.add(original_name)
        return original_name

    stem = Path(original_name).stem
    suffix = Path(original_name).suffix

    if strategy == "hash":
        raw_str = str(source_path.resolve()).encode("utf-8")
        path_hash = hashlib.md5(raw_str).hexdigest()[:8]  # nosec B324
        candidate = f"{stem}_{path_hash}{suffix}"
        if candidate not in used_names and not (dest_dir / candidate).exists():
            used_names.add(candidate)
            return candidate

    counter = 1
    while True:
        candidate = f"{stem}_{counter}{suffix}"
        if candidate not in used_names and not (dest_dir / candidate).exists():
            used_names.add(candidate)
            return candidate
        counter += 1


def collect_recent_files(
    source_dir: Path,
    dest_dir: Path,
    days: float,
    time_type: str = "mtime",
    extensions: Optional[List[str]] = None,
    collision_strategy: str = "counter",
    dry_run: bool = False,
    now: Optional[datetime] = None,
) -> List[Dict[str, str]]:
    """Scan source_dir and copy recent files to flat dest_dir.

    Args:
        source_dir: Source directory tree.
        dest_dir: Target flat destination directory.
        days: Days threshold.
        time_type: 'mtime' or 'ctime'.
        extensions: Optional list of extensions (e.g. ['.txt', '.pdf']).
        collision_strategy: 'counter' or 'hash'.
        dry_run: If True, simulate actions without copying.
        now: Optional reference datetime.

    Returns:
        List of manifest records describing processed files.
    """
    source_dir = Path(source_dir).resolve()
    dest_dir = Path(dest_dir).resolve()
    manifest: List[Dict[str, str]] = []
    used_names: Set[str] = set()

    if extensions:
        normalized_exts = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in extensions
        }
    else:
        normalized_exts = None

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    for root, _, files in os.walk(source_dir):
        for filename in files:
            file_path = Path(root) / filename

            # Skip dest_dir if inside source_dir
            try:
                if dest_dir in file_path.parents or file_path == dest_dir:
                    continue
            except ValueError:
                pass

            if normalized_exts and file_path.suffix.lower() not in normalized_exts:
                continue

            try:
                if not is_file_recent(file_path, days, time_type=time_type, now=now):
                    continue
            except OSError:
                continue

            unique_name = generate_unique_filename(
                dest_dir=dest_dir,
                original_name=file_path.name,
                used_names=used_names,
                source_path=file_path,
                strategy=collision_strategy,
            )

            target_path = dest_dir / unique_name
            ts = get_file_timestamp(file_path, time_type)
            iso_time = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            f_size = str(file_path.stat().st_size) if file_path.exists() else "0"

            record = {
                "source_path": str(file_path),
                "dest_path": str(target_path),
                "filename": unique_name,
                "timestamp_type": time_type,
                "timestamp_iso": iso_time,
                "file_size": f_size,
                "status": "dry_run" if dry_run else "copied",
            }

            if not dry_run:
                try:
                    shutil.copy2(file_path, target_path)
                except OSError as e:
                    record["status"] = f"failed: {e}"

            manifest.append(record)

    return manifest


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Copy recent files from a directory tree into a flat destination" + " folder."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--source", "-s", required=True, type=Path, help="Source directory path"
    )
    parser.add_argument(
        "--dest",
        "-d",
        required=True,
        type=Path,
        help="Destination directory path",
    )
    parser.add_argument(
        "--days",
        "-n",
        type=float,
        default=7.0,
        help="Filter files modified within N days",
    )
    parser.add_argument(
        "--time-type",
        choices=["mtime", "ctime"],
        default="mtime",
        help="Time attribute to filter by",
    )
    parser.add_argument(
        "--extensions",
        "-e",
        nargs="*",
        help="File extensions to include (e.g. .txt .pdf)",
    )
    parser.add_argument(
        "--collision-strategy",
        choices=["counter", "hash"],
        default="counter",
        help="Filename collision resolution",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifest.json"),
        help="Output manifest file path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without copying files",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for recent-files-collector."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    manifest_records = collect_recent_files(
        source_dir=parsed.source,
        dest_dir=parsed.dest,
        days=parsed.days,
        time_type=parsed.time_type,
        extensions=parsed.extensions,
        collision_strategy=parsed.collision_strategy,
        dry_run=parsed.dry_run,
    )

    print(f"Processed {len(manifest_records)} files.")
    if parsed.manifest:
        with open(parsed.manifest, "w", encoding="utf-8") as f:
            json.dump(manifest_records, f, indent=2)
        print(f"Manifest written to {parsed.manifest}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

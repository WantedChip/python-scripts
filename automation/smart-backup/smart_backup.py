#!/usr/bin/env python3
"""Smart Backup Script.

Performs incremental backups using file modification times or content
checksums. Supports exclusion rules, retention policies, dry-run mode,
and post-backup integrity verification.
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MANIFEST_FILENAME = ".backup_manifest.json"
DEFAULT_HASH_ALGO = "sha256"
CHUNK_SIZE = 1024 * 1024  # 1 MB


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FileRecord:
    """Record of a single backed-up file.

    Attributes:
        rel_path: Path relative to the backup source root.
        size_bytes: File size in bytes.
        mtime: Modification time (Unix timestamp).
        checksum: Hex digest of the file content.
        algo: Hash algorithm used.
    """

    rel_path: str
    size_bytes: int
    mtime: float
    checksum: str
    algo: str


@dataclass
class BackupManifest:
    """Manifest for a single backup run.

    Attributes:
        timestamp: ISO 8601 backup start time.
        source: Absolute source path.
        destination: Absolute destination path.
        algo: Hash algorithm.
        files: File records in this backup.
    """

    timestamp: str
    source: str
    destination: str
    algo: str
    files: List[FileRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "destination": self.destination,
            "algo": self.algo,
            "files": [
                {
                    "rel_path": f.rel_path,
                    "size_bytes": f.size_bytes,
                    "mtime": f.mtime,
                    "checksum": f.checksum,
                    "algo": f.algo,
                }
                for f in self.files
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupManifest":
        """Deserialize from dictionary."""
        manifest = cls(
            timestamp=data["timestamp"],
            source=data["source"],
            destination=data["destination"],
            algo=data.get("algo", DEFAULT_HASH_ALGO),
        )
        manifest.files = [
            FileRecord(
                rel_path=f["rel_path"],
                size_bytes=f["size_bytes"],
                mtime=f["mtime"],
                checksum=f["checksum"],
                algo=f.get("algo", manifest.algo),
            )
            for f in data.get("files", [])
        ]
        return manifest


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------


def compute_checksum(path: str, algo: str = DEFAULT_HASH_ALGO) -> str:
    """Compute the checksum of a file.

    Args:
        path: File path.
        algo: Hash algorithm name (e.g., 'sha256', 'md5').

    Returns:
        Hex digest string.

    Raises:
        OSError: If the file cannot be read.
    """
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def matches_exclusion(rel_path: str, patterns: List[str]) -> bool:
    """Check if a relative file path matches any exclusion pattern.

    Args:
        rel_path: Relative file path (using forward slashes).
        patterns: List of glob-style patterns or exact directory names.

    Returns:
        True if the path should be excluded.
    """
    import fnmatch

    for pattern in patterns:
        # Match against filename or full relative path
        if fnmatch.fnmatch(os.path.basename(rel_path), pattern):
            return True
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        # Check if any component of the path matches the pattern
        parts = Path(rel_path).parts
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def load_manifest(manifest_path: str) -> Optional[BackupManifest]:
    """Load a backup manifest from disk.

    Args:
        manifest_path: Path to the manifest JSON file.

    Returns:
        BackupManifest if found and valid, else None.
    """
    if not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            data = json.load(fh)
        return BackupManifest.from_dict(data)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Could not parse manifest '%s': %s", manifest_path, exc)
        return None


def save_manifest(manifest: BackupManifest, manifest_path: str) -> None:
    """Save a backup manifest to disk.

    Args:
        manifest: Manifest to save.
        manifest_path: Destination file path.
    """
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest.to_dict(), fh, indent=2)


# ---------------------------------------------------------------------------
# Backup logic
# ---------------------------------------------------------------------------


def collect_source_files(
    source: str,
    exclude_patterns: List[str],
) -> List[Tuple[str, str]]:
    """Walk source directory and collect files to back up.

    Args:
        source: Absolute source root.
        exclude_patterns: Exclusion glob patterns.

    Returns:
        List of (absolute_path, relative_path) tuples.
    """
    files: List[Tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(source, topdown=True):
        # Prune excluded directories in-place
        dirnames[:] = [
            d for d in dirnames
            if not matches_exclusion(
                os.path.relpath(os.path.join(dirpath, d), source).replace("\\", "/"),
                exclude_patterns,
            )
        ]
        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, source).replace("\\", "/")
            if not matches_exclusion(rel_path, exclude_patterns):
                files.append((abs_path, rel_path))
    return files


def should_copy(
    src_abs: str,
    rel_path: str,
    dest_abs: str,
    previous: Dict[str, FileRecord],
    mode: str,
    algo: str,
) -> bool:
    """Determine if a file needs to be copied.

    Args:
        src_abs: Absolute source file path.
        rel_path: Relative path (used for manifest lookup).
        dest_abs: Absolute destination file path.
        previous: Dict of rel_path → FileRecord from previous backup.
        mode: 'mtime' or 'checksum'.
        algo: Hash algorithm for checksum mode.

    Returns:
        True if the file should be copied.
    """
    if not os.path.exists(dest_abs):
        return True

    prev = previous.get(rel_path)
    if prev is None:
        return True

    src_mtime = os.path.getmtime(src_abs)
    src_size = os.path.getsize(src_abs)

    if mode == "mtime":
        return src_mtime != prev.mtime or src_size != prev.size_bytes
    else:  # checksum
        if src_mtime == prev.mtime and src_size == prev.size_bytes:
            return False  # Assume unchanged for speed
        return compute_checksum(src_abs, algo) != prev.checksum


def run_backup(
    source: str,
    destination: str,
    exclude_patterns: List[str],
    mode: str,
    algo: str,
    dry_run: bool,
) -> BackupManifest:
    """Execute an incremental backup.

    Args:
        source: Absolute source directory.
        destination: Absolute destination directory.
        exclude_patterns: Files/dirs to skip.
        mode: Comparison mode ('mtime' or 'checksum').
        algo: Hash algorithm.
        dry_run: If True, only simulate the backup.

    Returns:
        BackupManifest for this backup run.
    """
    manifest_path = os.path.join(destination, MANIFEST_FILENAME)
    prev_manifest = load_manifest(manifest_path)
    previous: Dict[str, FileRecord] = {}
    if prev_manifest:
        previous = {f.rel_path: f for f in prev_manifest.files}
        logger.info("Loaded previous manifest with %d files.", len(previous))

    files = collect_source_files(source, exclude_patterns)
    logger.info("Found %d source files to check.", len(files))

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = BackupManifest(
        timestamp=timestamp,
        source=source,
        destination=destination,
        algo=algo,
    )

    copied = skipped = errors = 0

    for src_abs, rel_path in files:
        dest_abs = os.path.join(destination, rel_path)

        try:
            src_mtime = os.path.getmtime(src_abs)
            src_size = os.path.getsize(src_abs)

            needs_copy = should_copy(src_abs, rel_path, dest_abs, previous, mode, algo)

            if dry_run:
                action = "COPY" if needs_copy else "SKIP"
                logger.info("[DRY-RUN] %s  %s", action, rel_path)
                if needs_copy:
                    copied += 1
                else:
                    skipped += 1
                # Still record to manifest for dry-run completeness
                checksum = prev_manifest.files[0].checksum if not needs_copy and previous.get(rel_path) else ""
                manifest.files.append(FileRecord(
                    rel_path=rel_path,
                    size_bytes=src_size,
                    mtime=src_mtime,
                    checksum=checksum,
                    algo=algo,
                ))
                continue

            if needs_copy:
                os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
                shutil.copy2(src_abs, dest_abs)
                checksum = compute_checksum(dest_abs, algo)
                copied += 1
                logger.info("Copied: %s", rel_path)
            else:
                # Inherit checksum from previous manifest
                checksum = previous[rel_path].checksum if rel_path in previous else ""
                skipped += 1

            manifest.files.append(FileRecord(
                rel_path=rel_path,
                size_bytes=src_size,
                mtime=src_mtime,
                checksum=checksum,
                algo=algo,
            ))

        except OSError as exc:
            logger.error("Error backing up '%s': %s", rel_path, exc)
            errors += 1

    if not dry_run:
        save_manifest(manifest, manifest_path)

    print(f"\n{'=' * 55}")
    print(f"  Backup {'(DRY-RUN) ' if dry_run else ''}Complete")
    print(f"  Source      : {source}")
    print(f"  Destination : {destination}")
    print(f"  Copied      : {copied}")
    print(f"  Skipped     : {skipped}")
    print(f"  Errors      : {errors}")
    print(f"{'=' * 55}\n")

    return manifest


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_backup(destination: str, algo: str) -> bool:
    """Verify backed-up files against the manifest checksums.

    Args:
        destination: Backup destination directory.
        algo: Hash algorithm.

    Returns:
        True if all files match, False if any mismatch or error.
    """
    manifest_path = os.path.join(destination, MANIFEST_FILENAME)
    manifest = load_manifest(manifest_path)
    if not manifest:
        logger.error("No manifest found in '%s'. Cannot verify.", destination)
        return False

    print(f"\nVerifying {len(manifest.files)} files…")
    ok = failed = missing = 0

    for record in manifest.files:
        dest_abs = os.path.join(destination, record.rel_path)
        if not os.path.exists(dest_abs):
            logger.warning("MISSING: %s", record.rel_path)
            missing += 1
            continue
        try:
            actual = compute_checksum(dest_abs, algo)
            if actual == record.checksum:
                ok += 1
            else:
                logger.error("MISMATCH: %s (expected %s, got %s)",
                             record.rel_path, record.checksum[:12], actual[:12])
                failed += 1
        except OSError as exc:
            logger.error("Cannot read '%s': %s", record.rel_path, exc)
            failed += 1

    print(f"  Verified OK : {ok}")
    print(f"  Mismatches  : {failed}")
    print(f"  Missing     : {missing}")
    all_ok = failed == 0 and missing == 0
    print(f"  Status      : {'✅ PASSED' if all_ok else '❌ FAILED'}\n")
    return all_ok


# ---------------------------------------------------------------------------
# Retention policy
# ---------------------------------------------------------------------------


def apply_retention(dest_root: str, keep_days: int, dry_run: bool) -> None:
    """Remove old backup snapshots beyond the retention window.

    Looks for timestamped subdirectories (ISO 8601 prefix) and deletes
    those older than keep_days.

    Args:
        dest_root: Parent directory containing dated snapshot folders.
        keep_days: Number of days to retain.
        dry_run: If True, only report what would be deleted.
    """
    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    iso_re = re.compile(r"^(\d{4}-\d{2}-\d{2})")
    deleted = 0

    for entry in os.scandir(dest_root):
        if not entry.is_dir():
            continue
        m = iso_re.match(entry.name)
        if not m:
            continue
        try:
            folder_date = datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            continue
        if folder_date < cutoff:
            if dry_run:
                print(f"[DRY-RUN] Would delete old backup: {entry.path}")
            else:
                shutil.rmtree(entry.path)
                print(f"Deleted old backup: {entry.path}")
            deleted += 1

    if deleted == 0:
        print("No old backups to clean up.")


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
        description="Smart Backup Script — incremental backups with checksums and verification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python smart_backup.py --source ~/Documents --dest /mnt/backup/docs
  python smart_backup.py --source . --dest /backup --mode checksum --verify
  python smart_backup.py --source . --dest /backup --dry-run
  python smart_backup.py --source . --dest /backup --exclude "*.log" "__pycache__"
  python smart_backup.py --dest /mnt/backup --apply-retention --keep-days 30
""",
    )
    parser.add_argument("--source", metavar="DIR", help="Source directory to back up.")
    parser.add_argument("--dest", required=True, metavar="DIR", help="Backup destination directory.")
    parser.add_argument(
        "--mode",
        choices=["mtime", "checksum"],
        default="mtime",
        help="Comparison mode: 'mtime' (fast) or 'checksum' (reliable). Default: mtime.",
    )
    parser.add_argument(
        "--algo",
        choices=["md5", "sha1", "sha256", "sha512"],
        default=DEFAULT_HASH_ALGO,
        help=f"Hash algorithm for checksums (default: {DEFAULT_HASH_ALGO}).",
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        default=[".git", "__pycache__", "*.pyc", ".DS_Store"],
        metavar="PATTERN",
        help="Glob patterns or directory names to exclude.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate backup without copying any files.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify backup integrity after completion.",
    )
    parser.add_argument(
        "--apply-retention",
        action="store_true",
        help="Delete old backup snapshots (requires --keep-days).",
    )
    parser.add_argument(
        "--keep-days",
        type=int,
        default=30,
        metavar="DAYS",
        help="Days to retain old backups when --apply-retention is set (default: 30).",
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
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    dest = os.path.abspath(args.dest)

    if args.apply_retention:
        apply_retention(dest, args.keep_days, args.dry_run)

    if args.source:
        source = os.path.abspath(args.source)
        if not os.path.isdir(source):
            logger.error("Source directory not found: %s", source)
            sys.exit(1)

        if not args.dry_run:
            os.makedirs(dest, exist_ok=True)

        manifest = run_backup(
            source=source,
            destination=dest,
            exclude_patterns=args.exclude,
            mode=args.mode,
            algo=args.algo,
            dry_run=args.dry_run,
        )

        if args.verify and not args.dry_run:
            ok = verify_backup(dest, args.algo)
            if not ok:
                sys.exit(1)
    elif not args.apply_retention:
        logger.error("Specify --source for a backup run, or --apply-retention to clean old backups.")
        sys.exit(1)


if __name__ == "__main__":
    main()

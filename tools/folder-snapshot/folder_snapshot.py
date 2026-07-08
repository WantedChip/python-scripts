#!/usr/bin/env python3
"""Folder Snapshot + Diff Tool.

Records a directory's state (file paths, sizes, hashes) as a snapshot,
and compares two snapshots — or a snapshot against the current live state —
to show what was added, removed, or modified.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1024 * 1024  # 1 MB
DEFAULT_ALGO = "sha256"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FileEntry:
    """A snapshot entry for a single file.

    Attributes:
        rel_path: File path relative to the snapshot root.
        size_bytes: File size in bytes.
        mtime: Last modification time (Unix timestamp).
        checksum: File content hash (hex digest), or empty string if skipped.
    """

    rel_path: str
    size_bytes: int
    mtime: float
    checksum: str


@dataclass
class Snapshot:
    """A point-in-time record of a directory's state.

    Attributes:
        root: Absolute path of the snapshotted directory.
        timestamp: ISO 8601 creation time.
        algo: Hash algorithm used.
        label: Optional human-readable label.
        files: Dict mapping rel_path → FileEntry.
    """

    root: str
    timestamp: str
    algo: str
    label: str
    files: Dict[str, FileEntry] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "root": self.root,
            "timestamp": self.timestamp,
            "algo": self.algo,
            "label": self.label,
            "files": {k: asdict(v) for k, v in self.files.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        """Deserialize from a dictionary."""
        snap = cls(
            root=data["root"],
            timestamp=data["timestamp"],
            algo=data.get("algo", DEFAULT_ALGO),
            label=data.get("label", ""),
        )
        snap.files = {
            k: FileEntry(**v) for k, v in data.get("files", {}).items()
        }
        return snap


@dataclass
class DiffResult:
    """Result of comparing two snapshots.

    Attributes:
        added: Files present in the new snapshot but not the old.
        removed: Files present in the old snapshot but not the new.
        modified: Files present in both but with changed size, mtime, or checksum.
        unchanged: Files that are identical in both snapshots.
    """

    added: List[FileEntry] = field(default_factory=list)
    removed: List[FileEntry] = field(default_factory=list)
    modified: List[Tuple[FileEntry, FileEntry]] = field(default_factory=list)
    unchanged: int = 0


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def compute_checksum(path: str, algo: str) -> str:
    """Compute the content hash of a file.

    Args:
        path: Absolute file path.
        algo: Hash algorithm name.

    Returns:
        Hex digest string, or empty string on error.
    """
    try:
        h = hashlib.new(algo)
        with open(path, "rb") as fh:
            while chunk := fh.read(CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        logger.warning("Cannot hash '%s': %s", path, exc)
        return ""


def take_snapshot(
    root: str,
    algo: str,
    label: str,
    exclude_patterns: List[str],
    no_hash: bool,
) -> Snapshot:
    """Record the current state of a directory as a snapshot.

    Args:
        root: Directory to snapshot.
        algo: Hash algorithm.
        label: Human-readable label for this snapshot.
        exclude_patterns: Glob patterns for files/dirs to skip.
        no_hash: If True, skip checksum computation (faster, less reliable diff).

    Returns:
        Populated Snapshot object.
    """
    import fnmatch

    snap = Snapshot(
        root=root,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        algo=algo,
        label=label,
    )

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Prune excluded directories
        dirnames[:] = [
            d for d in dirnames
            if not any(
                fnmatch.fnmatch(d, pat) for pat in exclude_patterns
            )
        ]

        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, root).replace("\\", "/")

            # Skip excluded files
            if any(fnmatch.fnmatch(filename, pat) for pat in exclude_patterns):
                continue

            try:
                stat = os.stat(abs_path)
                size = stat.st_size
                mtime = stat.st_mtime
            except OSError as exc:
                logger.warning("Cannot stat '%s': %s", abs_path, exc)
                continue

            checksum = "" if no_hash else compute_checksum(abs_path, algo)

            snap.files[rel_path] = FileEntry(
                rel_path=rel_path,
                size_bytes=size,
                mtime=mtime,
                checksum=checksum,
            )

    return snap


def save_snapshot(snap: Snapshot, output_path: str) -> None:
    """Save a snapshot to a JSON file.

    Args:
        snap: Snapshot to save.
        output_path: Destination file path.
    """
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(snap.to_dict(), fh, indent=2)
    logger.info("Snapshot saved to '%s' (%d files).", output_path, len(snap.files))


def load_snapshot(path: str) -> Snapshot:
    """Load a snapshot from a JSON file.

    Args:
        path: Path to the snapshot file.

    Returns:
        Deserialized Snapshot.

    Raises:
        SystemExit: If the file is missing or malformed.
    """
    if not os.path.isfile(path):
        logger.error("Snapshot file not found: %s", path)
        sys.exit(1)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return Snapshot.from_dict(data)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Cannot parse snapshot '%s': %s", path, exc)
        sys.exit(1)


def diff_snapshots(old: Snapshot, new: Snapshot, use_checksum: bool) -> DiffResult:
    """Compare two snapshots and return the differences.

    Args:
        old: The reference (older) snapshot.
        new: The comparison (newer) snapshot or live state.
        use_checksum: If True, use checksum comparison; otherwise mtime+size.

    Returns:
        DiffResult with categorised changes.
    """
    result = DiffResult()
    old_keys = set(old.files.keys())
    new_keys = set(new.files.keys())

    # Added files
    for k in new_keys - old_keys:
        result.added.append(new.files[k])

    # Removed files
    for k in old_keys - new_keys:
        result.removed.append(old.files[k])

    # Potentially modified
    for k in old_keys & new_keys:
        o = old.files[k]
        n = new.files[k]

        if use_checksum and o.checksum and n.checksum:
            changed = o.checksum != n.checksum
        else:
            changed = o.size_bytes != n.size_bytes or abs(o.mtime - n.mtime) > 1.0

        if changed:
            result.modified.append((o, n))
        else:
            result.unchanged += 1

    return result


def snapshot_current_state(old_snap: Snapshot, algo: str, no_hash: bool) -> Snapshot:
    """Take a live snapshot of the directory referenced by an existing snapshot.

    Args:
        old_snap: The reference snapshot (to get the root path).
        algo: Hash algorithm.
        no_hash: Skip checksum if True.

    Returns:
        Fresh Snapshot of the same root.
    """
    if not os.path.isdir(old_snap.root):
        logger.error("Original directory not found: %s", old_snap.root)
        sys.exit(1)
    return take_snapshot(old_snap.root, algo, "live", [], no_hash)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_diff(result: DiffResult, verbose: bool) -> None:
    """Print a human-readable diff report to stdout.

    Args:
        result: DiffResult to display.
        verbose: If True, show unchanged count too.
    """
    print()

    if result.added:
        print(f"  ✅ Added ({len(result.added)}):")
        for f in sorted(result.added, key=lambda x: x.rel_path):
            print(f"    + {f.rel_path}  ({_human(f.size_bytes)})")
    else:
        print("  ✅ Added: none")

    print()

    if result.removed:
        print(f"  ❌ Removed ({len(result.removed)}):")
        for f in sorted(result.removed, key=lambda x: x.rel_path):
            print(f"    - {f.rel_path}  ({_human(f.size_bytes)})")
    else:
        print("  ❌ Removed: none")

    print()

    if result.modified:
        print(f"  ✏  Modified ({len(result.modified)}):")
        for o, n in sorted(result.modified, key=lambda x: x[0].rel_path):
            size_delta = n.size_bytes - o.size_bytes
            sign = "+" if size_delta >= 0 else ""
            print(f"    ~ {o.rel_path}  ({_human(o.size_bytes)} → {_human(n.size_bytes)}, {sign}{_human(abs(size_delta))})")
    else:
        print("  ✏  Modified: none")

    print()
    print(f"{'=' * 55}")
    print(f"  Added    : {len(result.added)}")
    print(f"  Removed  : {len(result.removed)}")
    print(f"  Modified : {len(result.modified)}")
    if verbose:
        print(f"  Unchanged: {result.unchanged}")
    print(f"{'=' * 55}\n")


def _human(size_bytes: int) -> str:
    """Return a human-readable file size string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} TB"


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
        description="Folder Snapshot + Diff Tool — record directory state and compare changes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  snapshot  Record the current state of a directory.
  diff      Compare two snapshot files, or a snapshot against the live directory.

Examples:
  # Take a snapshot
  python folder_snapshot.py snapshot --root ./src --output before.json

  # Compare two snapshots
  python folder_snapshot.py diff --old before.json --new after.json

  # Compare snapshot against current state of the directory
  python folder_snapshot.py diff --old before.json --live

  # Skip checksum (faster, mtime-only comparison)
  python folder_snapshot.py diff --old before.json --live --no-hash
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # snapshot sub-command
    snap_parser = subparsers.add_parser("snapshot", help="Take a directory snapshot.")
    snap_parser.add_argument(
        "--root", required=True, metavar="DIR", help="Directory to snapshot."
    )
    snap_parser.add_argument(
        "--output", required=True, metavar="FILE", help="Output JSON file path."
    )
    snap_parser.add_argument(
        "--label", default="", metavar="TEXT", help="Optional label for this snapshot."
    )
    snap_parser.add_argument(
        "--algo",
        choices=["md5", "sha1", "sha256", "sha512"],
        default=DEFAULT_ALGO,
        help=f"Hash algorithm (default: {DEFAULT_ALGO}).",
    )
    snap_parser.add_argument(
        "--exclude",
        nargs="+",
        default=[".git", "__pycache__", "*.pyc"],
        metavar="PATTERN",
        help="Glob patterns or dir names to exclude.",
    )
    snap_parser.add_argument(
        "--no-hash",
        action="store_true",
        help="Skip checksum computation (faster snapshot, mtime-only diff).",
    )

    # diff sub-command
    diff_parser = subparsers.add_parser("diff", help="Compare two snapshots.")
    diff_parser.add_argument(
        "--old", required=True, metavar="FILE", help="Reference (older) snapshot file."
    )
    diff_parser.add_argument(
        "--new", metavar="FILE", help="Comparison (newer) snapshot file."
    )
    diff_parser.add_argument(
        "--live",
        action="store_true",
        help="Compare the old snapshot against the current live state of its directory.",
    )
    diff_parser.add_argument(
        "--algo",
        choices=["md5", "sha1", "sha256", "sha512"],
        default=DEFAULT_ALGO,
        help=f"Hash algorithm for live snapshots (default: {DEFAULT_ALGO}).",
    )
    diff_parser.add_argument(
        "--no-hash",
        action="store_true",
        help="Use mtime+size for comparison (skip checksum).",
    )
    diff_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show unchanged file count."
    )

    # Shared verbose for top-level
    parser.add_argument("--log-level", default="WARNING", help=argparse.SUPPRESS)

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    if args.command == "snapshot":
        root = os.path.abspath(args.root)
        if not os.path.isdir(root):
            logger.error("Directory not found: %s", root)
            sys.exit(1)

        print(f"Taking snapshot of '{root}'…")
        snap = take_snapshot(
            root=root,
            algo=args.algo,
            label=args.label,
            exclude_patterns=args.exclude,
            no_hash=args.no_hash,
        )
        save_snapshot(snap, args.output)
        print(f"✅ Snapshot saved to '{args.output}' ({len(snap.files)} files).")

    elif args.command == "diff":
        old_snap = load_snapshot(args.old)

        if args.live:
            print(f"Taking live snapshot of '{old_snap.root}'…")
            new_snap = snapshot_current_state(old_snap, args.algo, args.no_hash)
        elif args.new:
            new_snap = load_snapshot(args.new)
        else:
            logger.error("Specify either --new FILE or --live.")
            sys.exit(1)

        print(f"\nDiff: '{old_snap.label or args.old}' → '{new_snap.label or getattr(args, 'new', 'live')}'")
        print(f"  Old: {old_snap.timestamp} ({len(old_snap.files)} files)")
        print(f"  New: {new_snap.timestamp} ({len(new_snap.files)} files)")

        use_checksum = not args.no_hash
        result = diff_snapshots(old_snap, new_snap, use_checksum)
        print_diff(result, getattr(args, "verbose", False))


if __name__ == "__main__":
    main()

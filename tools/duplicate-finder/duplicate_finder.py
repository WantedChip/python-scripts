"""Duplicate File Finder.

Scans specified directories or files for duplicates using file content hashes.
Groups files by size first to optimize disk reads, then hashes only files of the
same size. Reports duplicates, wasted space, and optionally moves duplicates
to a quarantine directory, preserving relative paths and resolving name collisions.
"""

import argparse
import fnmatch
import hashlib
import logging
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union


def format_size(size_in_bytes: Union[int, float]) -> str:
    """Formats bytes into a human-readable string (e.g., KB, MB, GB).

    Args:
        size_in_bytes: Size in bytes to format.

    Returns:
        A human-readable string representation of the size.
    """
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    for unit in ["KB", "MB", "GB", "TB", "PB", "EB"]:
        size_in_bytes /= 1024.0
        if size_in_bytes < 1024:
            return f"{size_in_bytes:.2f} {unit}"
    return f"{size_in_bytes:.2f} ZB"


def calculate_hash(
    file_path: Path, hash_algo: str = "sha256", chunk_size: int = 65536
) -> str:
    """Calculates the hash of a file using chunked reading to save memory.

    Args:
        file_path: The Path of the file to hash.
        hash_algo: The hashing algorithm to use (md5, sha1, sha256).
        chunk_size: The chunk size in bytes for reading the file.

    Returns:
        The hex digest of the file contents.

    Raises:
        ValueError: If the hash algorithm is not supported.
        OSError: If there's an error reading the file.
    """
    try:
        hasher = hashlib.new(hash_algo)
    except ValueError as e:
        logging.error("Unsupported hash algorithm: %s", hash_algo)
        raise e

    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def should_exclude(path: Path, exclude_patterns: List[str]) -> bool:
    """Checks if a path matches any of the exclude glob patterns.

    Args:
        path: The path to check.
        exclude_patterns: List of shell-style glob patterns.

    Returns:
        True if the path matches any pattern, False otherwise.
    """
    path_str = str(path)
    path_name = path.name
    for pattern in exclude_patterns:
        # Match both the full path string and the base name
        if (
            fnmatch.fnmatch(path_name, pattern)
            or fnmatch.fnmatch(path_str, pattern)
            or any(fnmatch.fnmatch(part, pattern) for part in path.parts)
        ):
            return True
    return False


# pylint: disable=too-many-branches,too-many-nested-blocks
def scan_directories(
    paths: List[Path],
    min_size: int = 0,
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[int, List[Path]]:
    """Scans directories recursively and groups regular files by their size.

    Args:
        paths: A list of Paths to scan.
        min_size: The minimum file size in bytes to include.
        exclude_patterns: List of glob patterns to exclude from scanning.

    Returns:
        A dictionary mapping file sizes to lists of matching resolved file Paths.
    """
    if exclude_patterns is None:
        exclude_patterns = []

    files_by_size: Dict[int, List[Path]] = defaultdict(list)
    seen_resolved_paths: Set[Path] = set()

    for path in paths:
        if not path.exists():
            logging.warning("Path does not exist: %s", path)
            continue

        if should_exclude(path, exclude_patterns):
            logging.debug("Excluding input path: %s", path)
            continue

        if path.is_file():
            try:
                resolved = path.resolve()
                if resolved not in seen_resolved_paths:
                    size = resolved.stat().st_size
                    if size >= min_size:
                        files_by_size[size].append(resolved)
                        seen_resolved_paths.add(resolved)
            except OSError as e:
                logging.warning("Could not access file %s: %s", path, e)
            continue

        logging.info("Scanning directory: %s", path)
        for root, dirs, files in os.walk(path):
            # Prune directories in-place to avoid walking into excluded folders
            dirs[:] = [
                d for d in dirs if not should_exclude(Path(root) / d, exclude_patterns)
            ]

            for file in files:
                file_path = Path(root) / file
                if should_exclude(file_path, exclude_patterns):
                    continue

                try:
                    resolved = file_path.resolve()
                    if resolved not in seen_resolved_paths:
                        # Skip symlinks to avoid circular loops / double scanning
                        if resolved.is_file() and not resolved.is_symlink():
                            size = resolved.stat().st_size
                            if size >= min_size:
                                files_by_size[size].append(resolved)
                                seen_resolved_paths.add(resolved)
                except OSError as e:
                    logging.debug("Could not access %s: %s", file_path, e)

    return files_by_size


def find_duplicates(
    files_by_size: Dict[int, List[Path]],
    hash_algo: str = "sha256",
    strategy: str = "shortest-path",
) -> Tuple[List[Tuple[int, str, Path, List[Path]]], int]:
    """Identifies duplicate files by comparing content hashes of same-sized files.

    For each duplicate set, the "original" is determined based on the strategy:
    - shortest-path: The file with the shortest path length (alphabetical tie-breaker).
    - oldest: The file with the oldest modification time (mtime).
    - newest: The file with the newest modification time (mtime).

    Args:
        files_by_size: Dictionary mapping file sizes to lists of Paths.
        hash_algo: Hashing algorithm to use (md5, sha1, sha256).
        strategy: Strategy to pick the original ('shortest-path', 'oldest', 'newest').

    Returns:
        A tuple containing:
          - A list of duplicate groups, each represented as a tuple of:
            (file_size, file_hash, original_path, list_of_duplicate_paths)
          - The total wasted space in bytes.
    """
    duplicate_groups: List[Tuple[int, str, Path, List[Path]]] = []
    total_wasted_space = 0

    # Process larger files first
    for size, paths in sorted(files_by_size.items(), reverse=True):
        if len(paths) <= 1:
            continue

        logging.debug("Hashing %d files of size %d bytes...", len(paths), size)
        hashes: Dict[str, List[Path]] = defaultdict(list)
        for path in paths:
            try:
                h = calculate_hash(path, hash_algo)
                hashes[h].append(path)
            except OSError as e:
                logging.warning("Failed to calculate hash for %s: %s", path, e)
                continue

        for h, hashed_paths in hashes.items():
            if len(hashed_paths) <= 1:
                continue

            # Apply original selection strategy
            if strategy == "oldest":
                # Sort by mtime ascending (oldest first), break ties by path name
                hashed_paths.sort(
                    key=lambda p: (
                        p.stat().st_mtime if p.exists() else float("inf"),
                        str(p),
                    )
                )
            elif strategy == "newest":
                # Sort by mtime descending (newest first), break ties by path name
                hashed_paths.sort(
                    key=lambda p: (
                        -(p.stat().st_mtime) if p.exists() else float("inf"),
                        str(p),
                    )
                )
            else:  # default to shortest-path
                # Sort by path length ascending, break ties alphabetically
                hashed_paths.sort(key=lambda p: (len(str(p)), str(p)))

            original = hashed_paths[0]
            duplicates = hashed_paths[1:]

            duplicate_groups.append((size, h, original, duplicates))
            total_wasted_space += size * len(duplicates)

    return duplicate_groups, total_wasted_space


# pylint: disable=too-many-locals,too-many-branches
def quarantine_duplicates(
    duplicate_groups: List[Tuple[int, str, Path, List[Path]]],
    scan_roots: List[Path],
    quarantine_root: Path,
    dry_run: bool = False,
) -> int:
    """Moves duplicate files to a quarantine folder while resolving collisions.

    Maintains relative directory structure based on which scan root the file
    lives under. If a filename collision occurs, a suffix is appended.

    Args:
        duplicate_groups: The list of duplicate groups.
        scan_roots: The scan roots used to find the files (for relative path structure).
        quarantine_root: The target directory to quarantine files.
        dry_run: If True, log actions without modifying files.

    Returns:
        The number of successfully moved files.
    """
    quarantine_root = quarantine_root.resolve()
    resolved_scan_roots = [r.resolve() for r in scan_roots]

    if not dry_run:
        try:
            quarantine_root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.error(
                "Failed to create quarantine folder %s: %s", quarantine_root, e
            )
            return 0

    moved_count = 0

    for _, _, _, duplicates in duplicate_groups:
        for dup in duplicates:
            # Find matching scan root
            relative_path = None
            for scan_root in resolved_scan_roots:
                try:
                    relative_path = dup.relative_to(scan_root)
                    break
                except ValueError:
                    continue

            if relative_path is None:
                # If path was scanned directly as file, use its name
                relative_path = Path(dup.name)

            target_path = quarantine_root / relative_path

            # Collision resolution: append suffix if file exists
            if target_path.exists():
                suffix_counter = 1
                parent = target_path.parent
                stem = target_path.stem
                suffix = target_path.suffix
                while True:
                    candidate = parent / f"{stem}_{suffix_counter}{suffix}"
                    if not candidate.exists():
                        target_path = candidate
                        break
                    suffix_counter += 1

            action_desc = "Would move" if dry_run else "Moving"
            logging.info("%s: %s -> %s", action_desc, dup, target_path)

            if not dry_run:
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dup), str(target_path))
                    moved_count += 1
                except OSError as e:
                    logging.error("Failed to move %s to %s: %s", dup, target_path, e)
            else:
                moved_count += 1

    return moved_count


def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments.

    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="Scan directories for duplicate files by file hash."
    )
    parser.add_argument(
        "paths",
        type=Path,
        nargs="+",
        help="One or more directories (or files) to scan for duplicates.",
    )
    parser.add_argument(
        "-q",
        "--quarantine",
        type=Path,
        help=(
            "Move duplicate files to this directory "
            "instead of deleting or keeping them."
        ),
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Show what would be quarantined without actually moving any files.",
    )
    parser.add_argument(
        "--hash",
        choices=["md5", "sha1", "sha256"],
        default="sha256",
        help="Hashing algorithm to use (default: sha256).",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=0,
        help="Minimum file size in bytes to check (default: 0).",
    )
    parser.add_argument(
        "--strategy",
        choices=["shortest-path", "oldest", "newest"],
        default="shortest-path",
        help=(
            "Strategy to pick the 'original' file in a "
            "duplicate set (default: shortest-path)."
        ),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Shell-style wildcard patterns to exclude from "
            "scanning (can be repeated)."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase logging verbosity.",
    )
    return parser.parse_args()


# pylint: disable=too-many-locals
def main() -> None:
    """Main execution function."""
    # pylint: disable=duplicate-code
    # Standalone script design prioritized over sharing argparse/logging bootstrap.
    args = parse_arguments()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # Set default exclusions if none provided
    exclude_patterns = args.exclude
    if not exclude_patterns:
        exclude_patterns = [".git", ".venv", "__pycache__", "*.pyc"]

    # Resolve scan paths
    scan_paths = []
    for p in args.paths:
        try:
            scan_paths.append(p.resolve())
        except OSError as e:
            logging.error("Failed to resolve path %s: %s", p, e)

    logging.info("Starting duplicate file scan...")
    files_by_size = scan_directories(
        scan_paths, min_size=args.min_size, exclude_patterns=exclude_patterns
    )

    total_scanned_files = sum(len(paths) for paths in files_by_size.values())
    logging.info(
        "Scanned %d files with size >= %d bytes.",
        total_scanned_files,
        args.min_size,
    )

    duplicate_groups, wasted_space = find_duplicates(
        files_by_size, hash_algo=args.hash, strategy=args.strategy
    )

    # Print Report to standard output
    if not duplicate_groups:
        print("No duplicate files found.")
        return

    print("\n--- Duplicate Files Report ---")
    for size, file_hash, original, duplicates in duplicate_groups:
        print(f"\nSize: {format_size(size)} | Hash ({args.hash}): {file_hash}")
        print(f"  [Original]  {original}")
        for dup in duplicates:
            print(f"  [Duplicate] {dup}")

    print("\n--- Summary ---")
    print(f"Total duplicate groups: {len(duplicate_groups)}")
    total_dups = sum(len(dups) for _, _, _, dups in duplicate_groups)
    print(f"Total duplicate files:  {total_dups}")
    print(f"Total wasted space:     {format_size(wasted_space)}")

    # Move duplicates if quarantine directory is specified
    if args.quarantine:
        print("\n--- Quarantining Duplicates ---")
        moved = quarantine_duplicates(
            duplicate_groups,
            scan_roots=scan_paths,
            quarantine_root=args.quarantine,
            dry_run=args.dry_run,
        )
        status_word = "would be moved (dry run)" if args.dry_run else "moved"
        print(f"Result: {moved} of {total_dups} duplicate files {status_word}.")


if __name__ == "__main__":
    main()

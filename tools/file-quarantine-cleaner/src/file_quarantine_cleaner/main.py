"""File Quarantine Cleaner — local file system cleanup and quarantine utility."""

import argparse
import fnmatch
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("file_quarantine_cleaner")

INSTALLER_EXTS: Set[str] = {".msi", ".exe", ".dmg", ".pkg", ".deb", ".rpm"}
ARCHIVE_EXTS: Set[str] = {
    ".zip",
    ".tar.gz",
    ".tgz",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
}
CACHE_EXTS: Set[str] = {".tmp", ".temp", ".log", ".cache"}

DEFAULT_EXCLUDES: List[str] = [
    "**/node_modules/**",
    "**/.git/**",
    "**/.venv/**",
    "**/venv/**",
    "**/.mypy_cache/**",
    "**/.pytest_cache/**",
]


def setup_logging(verbose: bool) -> None:
    """Configure console logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)


def format_size(size_bytes: int) -> str:
    """Format file size in bytes to a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_file_info(file_path: Path, current_time: float) -> Dict[str, Any]:
    """Retrieve metadata about a file including size, age, and classification."""
    try:
        stat_info = file_path.stat()
        size = stat_info.st_size
        mtime = stat_info.st_mtime
        age_days = (current_time - mtime) / (24 * 3600)
    except OSError as e:
        logger.debug("Failed to read metadata for %s: %s", file_path, e)
        return {}

    suffix = file_path.suffix.lower()
    categories: List[str] = []

    if suffix in INSTALLER_EXTS:
        categories.append("installer")
    if suffix in ARCHIVE_EXTS:
        categories.append("archive")
    if suffix in CACHE_EXTS or "cache" in file_path.parts:
        categories.append("cache")

    # If no specific categories but age matches abandoned criteria
    if not categories:
        categories.append("abandoned")

    return {
        "path": file_path,
        "size": size,
        "age_days": max(0.0, age_days),
        "categories": categories,
    }


def scan_directory(
    directory: Path,
    days_threshold: float,
    excludes: List[str],
    categories_filter: Set[str],
    current_time: float,
) -> List[Dict[str, Any]]:
    """Scan the directory recursively, matching criteria and filtering exclusions."""
    # pylint: disable=too-many-locals,too-many-branches
    matching_files: List[Dict[str, Any]] = []
    if not directory.exists() or not directory.is_dir():
        logger.error("Target directory does not exist or is not a directory.")
        return matching_files

    exclude_patterns = DEFAULT_EXCLUDES + excludes

    for root, _, files in os.walk(directory):
        root_path = Path(root)

        # Check if the directory path matches any exclusion patterns
        should_skip_dir = False
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(str(root_path), pattern) or fnmatch.fnmatch(
                root_path.name, pattern
            ):
                should_skip_dir = True
                break
        if should_skip_dir:
            continue

        for file in files:
            file_path = root_path / file

            # Check exclusion patterns for the file
            should_exclude = False
            for pattern in exclude_patterns:
                # Support matching full path or relative path
                try:
                    rel_path = file_path.relative_to(directory)
                    if fnmatch.fnmatch(str(rel_path), pattern) or fnmatch.fnmatch(
                        str(file_path), pattern
                    ):
                        should_exclude = True
                        break
                except ValueError:
                    if fnmatch.fnmatch(str(file_path), pattern):
                        should_exclude = True
                        break
            if should_exclude:
                continue

            file_info = get_file_info(file_path, current_time)
            if not file_info:
                continue

            # Verify age matches threshold
            if file_info["age_days"] < days_threshold:
                # If it's a specific cache or installer, we might still match
                # but default download cleanup needs to be older than threshold
                if "abandoned" in file_info["categories"]:
                    continue

            # Filter categories
            if categories_filter and not any(
                cat in categories_filter for cat in file_info["categories"]
            ):
                continue

            matching_files.append(file_info)

    return matching_files


def handle_quarantine(file_path: Path, quarantine_dir: Path, dry_run: bool) -> bool:
    """Move file to quarantine preserving relative structure or resolving conflicts."""
    try:
        if not dry_run:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            # Resolve name conflicts in quarantine dir
            dest = quarantine_dir / file_path.name
            counter = 1
            while dest.exists():
                dest = quarantine_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
                counter += 1

            shutil.move(str(file_path), str(dest))
        logger.info("[QUARANTINED] Moved %s to %s", file_path.name, quarantine_dir)
        return True
    except OSError as e:
        logger.error("Failed to quarantine %s: %s", file_path, e)
        return False


def handle_deletion(file_path: Path, dry_run: bool) -> bool:
    """Remove file from filesystem."""
    try:
        if not dry_run:
            file_path.unlink()
        logger.info("[DELETED] Removed %s", file_path)
        return True
    except OSError as e:
        logger.error("Failed to delete %s: %s", file_path, e)
        return False


def run_cleanup(
    files: List[Dict[str, Any]],
    quarantine_dir: Optional[Path],
    dry_run: bool,
    force: bool,
) -> Tuple[int, int]:
    """Interactively or automatically deletes or quarantines files."""
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    cleaned_count = 0
    total_cleaned_size = 0

    if not files:
        logger.info("No files matching criteria were found.")
        return cleaned_count, total_cleaned_size

    total_size = sum(f["size"] for f in files)
    action_verb = "quarantine" if quarantine_dir else "delete"
    logger.info(
        "Identified %d files (%s) to %s.",
        len(files),
        format_size(total_size),
        action_verb,
    )

    if dry_run:
        logger.info("Dry-run mode active. No changes will be written.")

    # Sort files by size descending
    files_sorted = sorted(files, key=lambda x: x["size"], reverse=True)

    # If not forced, prompt the user
    confirm_all = force
    interactive = False

    if not force:
        try:
            print("Select cleanup method:")
            print("  [y] Clean all detected files")
            print("  [n] Abort cleanup")
            print("  [i] Interactive confirmation (ask for each file)")
            response = input("Choice [y/n/i]: ").strip().lower()
            if response == "y":
                confirm_all = True
            elif response == "i":
                interactive = True
            else:
                logger.info("Cleanup aborted by user.")
                return cleaned_count, total_cleaned_size
        except (KeyboardInterrupt, EOFError):
            print()
            logger.info("Cleanup aborted by user.")
            return cleaned_count, total_cleaned_size

    for file_info in files_sorted:
        file_path = file_info["path"]
        size = file_info["size"]

        should_act = confirm_all
        if interactive:
            try:
                print(
                    f"\nFile: {file_path}\n"
                    f"Size: {format_size(size)} | "
                    f"Age: {file_info['age_days']:.1f} days\n"
                    f"Categories: {', '.join(file_info['categories'])}"
                )
                res = input(f"Confirm {action_verb} [y/N]: ").strip().lower()
                should_act = res == "y"
            except (KeyboardInterrupt, EOFError):
                print()
                logger.info("Interactive cleanup paused by user.")
                break

        if should_act:
            success = False
            if quarantine_dir:
                success = handle_quarantine(file_path, quarantine_dir, dry_run)
            else:
                success = handle_deletion(file_path, dry_run)

            if success:
                cleaned_count += 1
                total_cleaned_size += size

    action_past_tense = "quarantined" if quarantine_dir else "deleted"
    logger.info(
        "Successfully %s %d files (total size: %s).",
        action_past_tense,
        cleaned_count,
        format_size(total_cleaned_size),
    )
    return cleaned_count, total_cleaned_size


def main() -> None:
    """CLI entry point for File Quarantine Cleaner."""
    import time  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(
        description=(
            "Identify and clean/quarantine temporary files, "
            "installers, and abandoned downloads."
        )
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=str,
        help="Target directory to scan (defaults to standard User Downloads folder)",
    )
    parser.add_argument(
        "--days",
        type=float,
        default=30.0,
        help="Age threshold in days for abandoned files (default: 30)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob exclusion pattern to ignore during scanning",
    )
    parser.add_argument(
        "--quarantine-dir",
        type=str,
        help="Optional directory to quarantine files in instead of direct deletion",
    )
    parser.add_argument(
        "--category",
        action="append",
        choices=["installer", "archive", "cache", "abandoned"],
        help="Only target files belonging to specific categories (repeatable)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report identified files but do not make changes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clean all identified files without asking for confirmation",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed log descriptions",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Resolve scan directory
    scan_path_str = args.directory
    if not scan_path_str:
        # Default to Downloads directory
        scan_path = Path.home() / "Downloads"
        logger.info("No directory specified. Defaulting to: %s", scan_path)
    else:
        scan_path = Path(scan_path_str)

    if not scan_path.exists():
        logger.error("Scan directory does not exist: %s", scan_path)
        sys.exit(1)

    categories_filter = set(args.category) if args.category else set()
    quarantine_path = Path(args.quarantine_dir) if args.quarantine_dir else None

    current_time = time.time()
    logger.info("Scanning directory: %s ...", scan_path)
    files = scan_directory(
        scan_path,
        args.days,
        args.exclude,
        categories_filter,
        current_time,
    )

    # Show scanning details
    if files:
        print(f"{'PATH':<60} | {'SIZE':<10} | {'AGE (DAYS)':<10} | {'CATEGORIES':<20}")
        print("-" * 110)
        for f in sorted(files, key=lambda x: x["size"], reverse=True):
            path_str = str(f["path"])
            if len(path_str) > 57:
                path_str = "..." + path_str[-54:]
            cats = ",".join(f["categories"])
            print(
                f"{path_str:<60} | {format_size(f['size']):<10} | "
                f"{f['age_days']:<10.1f} | {cats:<20}"
            )
        print("-" * 110)

    run_cleanup(files, quarantine_path, args.dry_run, args.force)


if __name__ == "__main__":
    main()

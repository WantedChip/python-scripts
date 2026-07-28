"""Organize screenshots into date-stamped directories and rename them systematically.

This module scans source folders for screenshot image files, categorizes them into
year-month date folders (e.g., '2026-07/'), and renames files cleanly with timestamps.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
from datetime import datetime
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SCREENSHOT_KEYWORDS = {"screenshot", "screen shot", "captura", "scrn", "prtscr"}


def is_screenshot_file(file_path: Path) -> bool:
    """Determine if a file is a screenshot based on name or metadata.

    Args:
        file_path: File Path object to evaluate.

    Returns:
        True if file matches screenshot naming patterns, False otherwise.
    """
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False

    name_lower = file_path.name.lower()
    return any(keyword in name_lower for keyword in SCREENSHOT_KEYWORDS)


def get_file_creation_date(file_path: Path) -> datetime:
    """Get the earliest creation/modification datetime of a file.

    Args:
        file_path: File Path object.

    Returns:
        datetime object corresponding to file creation or modification time.
    """
    stat = file_path.stat()
    timestamp = getattr(stat, "st_ctime", stat.st_mtime)
    return datetime.fromtimestamp(timestamp)


def organize_screenshots(
    source_dir: Path,
    target_dir: Path,
    date_format: str = "%Y-%m",
    prefix: str = "Screenshot_",
    dry_run: bool = False,
) -> Tuple[int, int]:
    """Scan and organize screenshots into date folders.

    Args:
        source_dir: Directory to scan for screenshots.
        target_dir: Destination root directory for organized folders.
        date_format: Subfolder strftime date format (e.g. '%Y-%m').
        prefix: New file name prefix.
        dry_run: If True, simulates moves without modifying disk.

    Returns:
        Tuple of (success_count, skipped_count).
    """
    if not source_dir.exists() or not source_dir.is_dir():
        logger.error("Source directory does not exist: %s", source_dir)
        return (0, 0)

    screenshot_files: List[Path] = []
    for root, _, files in os.walk(source_dir):
        for fname in files:
            fp = Path(root) / fname
            if is_screenshot_file(fp):
                screenshot_files.append(fp)

    if not screenshot_files:
        logger.warning("No screenshot files found in %s", source_dir)
        return (0, 0)

    moved_count = 0
    skipped_count = 0

    for src in screenshot_files:
        try:
            c_date = get_file_creation_date(src)
            folder_name = c_date.strftime(date_format)
            file_stamp = c_date.strftime("%Y%m%d_%H%M%S")

            subfolder = target_dir / folder_name
            new_name = f"{prefix}{file_stamp}{src.suffix.lower()}"
            dst = subfolder / new_name

            # Avoid overwriting existing files by appending counter
            counter = 1
            while dst.exists() and dst != src:
                new_name = f"{prefix}{file_stamp}_{counter}{src.suffix.lower()}"
                dst = subfolder / new_name
                counter += 1

            if not dry_run:
                subfolder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))

            logger.info("Organized: %s -> %s", src.name, dst)
            moved_count += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Failed organizing screenshot %s: %s", src, exc)
            skipped_count += 1

    return (moved_count, skipped_count)


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Organize screenshots into date-stamped directories."
    )
    parser.add_argument(
        "source",
        type=str,
        help="Source directory path containing screenshots.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output target directory path. Defaults to source location.",
    )
    parser.add_argument(
        "-p",
        "--prefix",
        type=str,
        default="Screenshot_",
        help="Prefix for renamed screenshot files (default: 'Screenshot_').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate actions without moving files.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging.",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point.

    Args:
        args: Argument list or None for sys.argv[1:].

    Returns:
        Exit code integer (0 for success, non-zero for error).
    """
    parser = setup_cli_parser()
    parsed_args = parser.parse_args(args)

    log_level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    source_path = Path(parsed_args.source)
    target_path = Path(parsed_args.output) if parsed_args.output else source_path

    moved, skipped = organize_screenshots(
        source_path,
        target_path,
        prefix=parsed_args.prefix,
        dry_run=parsed_args.dry_run,
    )

    logger.info("Organized %d screenshots (%d skipped).", moved, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())

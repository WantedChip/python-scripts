"""Downloads Folder Auto-Organizer.

Watches a specified directory or scans it on-demand, sorting files into
categorized subfolders based on extension, date, or filename patterns.
Uses the watchdog library if running in active watch mode.
"""

import argparse
from datetime import datetime
import fnmatch
import json
import logging
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Set

# Optional watchdog integration
try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

# Default configuration rules
DEFAULT_CONFIG = {
    "rules": [
        {
            "name": "Images",
            "extensions": [
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".bmp",
                ".svg",
                ".webp",
                ".heic",
            ],
        },
        {
            "name": "Documents",
            "extensions": [
                ".pdf",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx",
                ".ppt",
                ".pptx",
                ".txt",
                ".rtf",
                ".csv",
                ".odt",
                ".ods",
                ".odp",
            ],
        },
        {
            "name": "Audio",
            "extensions": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"],
        },
        {
            "name": "Video",
            "extensions": [".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"],
        },
        {
            "name": "Archives",
            "extensions": [".zip", ".tar", ".gz", ".rar", ".7z", ".tgz", ".bz2"],
        },
        {
            "name": "Executables",
            "extensions": [".exe", ".msi", ".dmg", ".pkg", ".sh", ".bat", ".bin"],
        },
    ],
    "default_category": "Others",
    "temp_extensions": [".crdownload", ".part", ".tmp", ".download"],
    "ignored_patterns": [".*", "desktop.ini", "Thumbs.db"],
}


# pylint: disable=too-many-instance-attributes
class FolderOrganizer:
    """Class to manage the file scanning and sorting logic."""

    source: Path
    destination: Path
    conflict_strategy: str
    date_grouping: bool
    dry_run: bool
    config: Dict[str, Any]
    temp_exts: Set[str]
    ignored_patterns: List[str]
    default_category: str
    destination_dirs: Set[Path]
    stability_check: bool
    stability_delay: float
    stability_retries: int

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(
        self,
        source: Path,
        destination: Optional[Path] = None,
        config_path: Optional[Path] = None,
        conflict_strategy: str = "rename",
        date_grouping: bool = False,
        dry_run: bool = False,
        stability_check: bool = True,
        stability_delay: float = 0.5,
        stability_retries: int = 3,
    ) -> None:
        """Initializes the FolderOrganizer with settings and configurations.

        Args:
            source: Path to the directory to scan/watch.
            destination: Path where organized folders will be placed.
            config_path: Path to custom JSON configuration.
            conflict_strategy: Conflict resolution ('rename', 'overwrite', 'skip').
            date_grouping: If True, sub-group files by year-month within categories.
            dry_run: If True, only log proposed changes without moving files.
            stability_check: If True, check files are stable before organizing.
            stability_delay: Delay in seconds between stability checks.
            stability_retries: Number of retries for stability check.
        """
        self.source = source.resolve()
        self.destination = (
            destination.resolve() if destination else self.source
        )
        self.conflict_strategy = conflict_strategy
        self.date_grouping = date_grouping
        self.dry_run = dry_run
        self.stability_check = stability_check
        self.stability_delay = stability_delay
        self.stability_retries = stability_retries

        self.config = self._load_config(config_path)

        # Prepare helper sets/lists for fast checking
        self.temp_exts = {
            ext.lower() for ext in self.config.get("temp_extensions", [])
        }
        self.ignored_patterns = self.config.get("ignored_patterns", [])
        self.default_category = self.config.get("default_category", "Others")

        # Set of destination paths to avoid scanning files that are already sorted
        # if destination is a subfolder of source.
        self.destination_dirs: Set[Path] = set()
        for rule in self.config.get("rules", []):
            self.destination_dirs.add(self.destination / rule["name"])
        self.destination_dirs.add(self.destination / self.default_category)

    def _load_config(self, config_path: Optional[Path]) -> Dict[str, Any]:
        """Loads configuration from file, falling back to defaults.

        Args:
            config_path: Optional path to JSON config.

        Returns:
            Dictionary containing layout configuration.
        """
        if not config_path:
            logging.info("Using default organization config.")
            return DEFAULT_CONFIG

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                custom_config = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(
                f"Error: Failed to load custom config from {config_path}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Validate custom_config schema
        if not isinstance(custom_config, dict):
            print("Error: Configuration must be a JSON object.", file=sys.stderr)
            sys.exit(1)

        if "rules" not in custom_config:
            print("Error: Configuration is missing the 'rules' key.", file=sys.stderr)
            sys.exit(1)

        if not isinstance(custom_config["rules"], list):
            print("Error: 'rules' in configuration must be a list.", file=sys.stderr)
            sys.exit(1)

        for idx, rule in enumerate(custom_config["rules"]):
            if not isinstance(rule, dict):
                print(
                    f"Error: Rule at index {idx} is not a JSON object.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if "name" not in rule:
                print(
                    f"Error: Rule at index {idx} is missing the 'name' key.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if "extensions" not in rule and "patterns" not in rule:
                print(
                    f"Error: Rule '{rule.get('name', idx)}' must contain "
                    "either 'extensions' or 'patterns'.",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Merge custom config with default structure for safety
        config = DEFAULT_CONFIG.copy()
        config.update(custom_config)
        logging.info("Successfully loaded custom config from %s", config_path)
        return config

    def should_ignore(self, path: Path) -> bool:
        """Checks if a path should be ignored (ignored patterns, temp files, folders).

        Args:
            path: Path to evaluate.

        Returns:
            True if path should be ignored, False otherwise.
        """
        if not path.exists():
            return True

        if path.is_dir():
            return True

        # Check ignored file pattern
        name = path.name
        for pattern in self.ignored_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True

        # Check temporary download extension
        if path.suffix.lower() in self.temp_exts:
            return True

        # If destination is inside source, ignore already organized files
        resolved_path = path.resolve()
        for dest_dir in self.destination_dirs:
            try:
                # If path is inside dest_dir, ignore it
                resolved_path.relative_to(dest_dir)
                return True
            except ValueError:
                continue

        return False

    def classify_file(self, path: Path) -> str:
        """Determines the category name for a given file.

        Args:
            path: Path to analyze.

        Returns:
            Category folder name.
        """
        ext = path.suffix.lower()
        name = path.name

        # Iterate through rules in config
        for rule in self.config.get("rules", []):
            # Check extensions match
            if "extensions" in rule and ext in {
                e.lower() for e in rule["extensions"]
            }:
                return rule["name"]

            # Check filename glob patterns match
            if "patterns" in rule:
                for pattern in rule["patterns"]:
                    if fnmatch.fnmatch(name, pattern):
                        return rule["name"]

        return self.default_category

    def is_file_stable(
        self,
        path: Path,
        delay: Optional[float] = None,
        retries: Optional[int] = None,
    ) -> bool:
        """Ensures file is fully written and not locked by another process.

        Args:
            path: File path to check.
            delay: Seconds to sleep between checks.
            retries: Number of stability check iterations.

        Returns:
            True if file is stable and ready to move, False otherwise.
        """
        if not self.stability_check:
            return True

        if not path.exists():
            return False

        delay_val = delay if delay is not None else self.stability_delay
        retries_val = retries if retries is not None else self.stability_retries

        last_size = -1
        for _ in range(retries_val):
            if not path.exists():
                return False
            try:
                current_size = path.stat().st_size
                if current_size == last_size:
                    # Check lock state by attempting to open file in append mode
                    with open(path, "ab"):
                        pass
                    return True
                last_size = current_size
            except (OSError, PermissionError):
                # File is locked / in-use
                pass
            time.sleep(delay_val)
        return False

    def resolve_conflict(self, target_path: Path) -> Optional[Path]:
        """Resolves filename conflict based on conflict_strategy.

        Args:
            target_path: Proposed destination path.

        Returns:
            Resolved Path if move should proceed, None to skip.
        """
        if not target_path.exists():
            return target_path

        if self.conflict_strategy == "overwrite":
            logging.warning("File conflict: %s will be overwritten.", target_path)
            return target_path

        if self.conflict_strategy == "skip":
            logging.info("File conflict: Skipping %s", target_path.name)
            return None

        # default: rename with suffix
        parent = target_path.parent
        stem = target_path.stem
        suffix = target_path.suffix
        counter = 1

        while True:
            candidate = parent / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def organize_file(self, path: Path) -> bool:
        """Classifies and moves a single file to its destination folder.

        Args:
            path: File path to organize.

        Returns:
            True if file was successfully moved/processed, False otherwise.
        """
        if self.should_ignore(path):
            return False

        # Classify the file
        category = self.classify_file(path)

        # Build target directory structure
        target_dir = self.destination / category

        if self.date_grouping:
            try:
                # Use modification time for date grouping
                mtime = path.stat().st_mtime
                date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m")
                target_dir = target_dir / date_str
            except OSError as e:
                logging.error("Failed to read file timestamp for %s: %s", path, e)

        # Resolve conflict
        target_path = target_dir / path.name
        final_dest = self.resolve_conflict(target_path)

        if not final_dest:
            return False

        action_desc = "[DRY RUN] Would move" if self.dry_run else "Moving"
        logging.info("%s: %s -> %s", action_desc, path, final_dest)

        if not self.dry_run:
            try:
                # Ensure the destination directory exists
                final_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(final_dest))
                return True
            except OSError as e:
                logging.error("Failed to move %s to %s: %s", path, final_dest, e)
                return False
        return True

    def scan_and_organize(self) -> int:
        """Scans the source directory and organizes all matching files.

        Returns:
            Number of organized files.
        """
        logging.info("Scanning source directory: %s", self.source)
        if not self.source.exists() or not self.source.is_dir():
            logging.error(
                "Source directory %s does not exist or is not a directory.",
                self.source,
            )
            return 0

        organized_count = 0
        try:
            # Only iterate through files in the immediate directory to avoid
            # recursively reorganizing user-managed subfolders.
            for item in self.source.iterdir():
                if not item.is_file():
                    continue
                # Check stability first so on-demand scans don't grab active writes
                if self.should_ignore(item):
                    continue
                if not self.is_file_stable(item):
                    continue
                if self.organize_file(item):
                    organized_count += 1
        except OSError as e:
            logging.error("Error accessing directory %s: %s", self.source, e)

        logging.info("Scan complete. Organized %d files.", organized_count)
        return organized_count


# FileSystem event handler for Watchdog mode
if HAS_WATCHDOG:
    BaseWatchHandler = FileSystemEventHandler
else:
    BaseWatchHandler = object  # type: ignore


class DownloadWatchHandler(BaseWatchHandler):  # pylint: disable=too-few-public-methods
    """Watchdog handler for reacting to new/renamed files."""

    def __init__(self, organizer: FolderOrganizer) -> None:
        self.organizer = organizer

    def on_created(self, event: Any) -> None:
        """Event handler for file creation events."""
        if event.is_directory:
            return
        path = Path(event.src_path)
        logging.debug("Watchdog: file created event for %s", path)
        if self.organizer.should_ignore(path):
            return
        # Wait for writing to stabilize
        if self.organizer.is_file_stable(path):
            self.organizer.organize_file(path)

    def on_moved(self, event: Any) -> None:
        """Event handler for file move/rename events."""
        if event.is_directory:
            return
        path = Path(event.dest_path)
        logging.debug("Watchdog: file moved/renamed event to %s", path)
        if self.organizer.should_ignore(path):
            return
        # Wait for writing to stabilize
        if self.organizer.is_file_stable(path):
            self.organizer.organize_file(path)


def run_watch_mode(organizer: FolderOrganizer) -> None:
    """Starts the watchdog observer to actively monitor directory changes.

    Args:
        organizer: Instantiated FolderOrganizer.
    """
    if not HAS_WATCHDOG:
        logging.error(
            "Watchdog library is not installed. Active watch mode is unavailable.\n"
            "Please install watchdog to run in this mode: pip install watchdog"
        )
        sys.exit(1)

    if not organizer.source.exists() or not organizer.source.is_dir():
        logging.error(
            "Source directory %s does not exist or is not a directory.",
            organizer.source,
        )
        print(
            f"Error: Source directory {organizer.source} does not exist "
            "or is not a directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Initial scan before active watching to clean up pre-existing files
    logging.info("Performing initial cleanup scan before entering active watch...")
    organizer.scan_and_organize()

    observer = Observer()
    handler = DownloadWatchHandler(organizer)
    # Watch non-recursively to avoid monitoring already organized folders
    observer.schedule(handler, path=str(organizer.source), recursive=False)
    observer.start()

    logging.info("Actively watching directory: %s", organizer.source)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping watch observer...")
        observer.stop()
    observer.join()


def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments.

    Returns:
        argparse Namespace.
    """
    parser = argparse.ArgumentParser(
        description="Downloads Folder Auto-Organizer: Sorts files into folders."
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Directory to organize (default: current directory).",
    )
    parser.add_argument(
        "-d",
        "--destination",
        type=Path,
        help=(
            "Destination directory where files should be moved "
            "(default: same as source)."
        ),
    )
    parser.add_argument(
        "-w",
        "--watch",
        action="store_true",
        help="Run continuously, watching the source directory for new files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without actually moving files.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help=(
            "Path to a JSON configuration file defining custom "
            "categorization rules."
        ),
    )
    parser.add_argument(
        "--conflict",
        choices=["rename", "overwrite", "skip"],
        default="rename",
        help=(
            "Conflict resolution strategy when target file already exists "
            "(default: rename)."
        ),
    )
    parser.add_argument(
        "--date-grouping",
        action="store_true",
        help=(
            "Sub-group files inside categories by creation/modification date "
            "(e.g., Category/YYYY-MM/)."
        ),
    )
    parser.add_argument(
        "--no-stability-check",
        action="store_true",
        help="Disable stability checks entirely.",
    )
    parser.add_argument(
        "--stability-delay",
        type=float,
        default=0.5,
        help="Seconds to sleep between stability checks (default: 0.5).",
    )
    parser.add_argument(
        "--stability-retries",
        type=int,
        default=6,
        help="Number of stability check iterations (default: 6).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    return parser.parse_args()


def main() -> None:
    """Main program entry point."""
    args = parse_arguments()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    organizer = FolderOrganizer(
        source=args.source,
        destination=args.destination,
        config_path=args.config,
        conflict_strategy=args.conflict,
        date_grouping=args.date_grouping,
        dry_run=args.dry_run,
        stability_check=not args.no_stability_check,
        stability_delay=args.stability_delay,
        stability_retries=args.stability_retries,
    )

    if args.watch:
        run_watch_mode(organizer)
    else:
        organizer.scan_and_organize()


if __name__ == "__main__":
    main()

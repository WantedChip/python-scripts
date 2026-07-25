"""Backup Rotation Manager.

Manages backup files in a directory by retaining backups based on count, daily,
or weekly retention policies, and purging older ones.
"""

import argparse
import datetime
import fnmatch
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class BackupFile:
    """Represents a single backup file and its metadata."""

    def __init__(self, path: Path) -> None:
        self.path: Path = path
        self.mtime: datetime.datetime = datetime.datetime.fromtimestamp(
            path.stat().st_mtime
        )
        self.size_bytes: int = path.stat().st_size

    @property
    def date(self) -> datetime.date:
        """Returns the modification date of the backup file."""
        return self.mtime.date()

    @property
    def year_week(self) -> Tuple[int, int]:
        """Returns (year, week_number) of the backup file."""
        iso = self.mtime.isocalendar()
        return (iso[0], iso[1])

    def __repr__(self) -> str:
        return f"<BackupFile {self.path.name} mtime={self.mtime.isoformat()}>"


class BackupRotationManager:
    """Manages discovery and purging of backup files according to retention policies."""

    def __init__(self, directory: Path, pattern: str = "*") -> None:
        self.directory: Path = Path(directory)
        self.pattern: str = pattern

    def list_backups(self) -> List[BackupFile]:
        """Lists matching files in target directory, sorted newest first."""
        if not self.directory.exists() or not self.directory.is_dir():
            raise ValueError(
                f"Directory '{self.directory}' does not exist or is not a directory."
            )

        backups: List[BackupFile] = []
        for entry in self.directory.iterdir():
            if entry.is_file() and fnmatch.fnmatch(entry.name, self.pattern):
                backups.append(BackupFile(entry))

        # Sort descending by modification time (newest first)
        backups.sort(key=lambda b: b.mtime, reverse=True)
        return backups

    def determine_retained_backups(
        self,
        backups: List[BackupFile],
        keep_count: Optional[int] = None,
        keep_daily: Optional[int] = None,
        keep_weekly: Optional[int] = None,
    ) -> Tuple[Set[Path], Set[Path]]:
        """Determines which backups to retain and which to purge.

        Returns:
            Tuple[Set[Path], Set[Path]]: (retained_paths, purged_paths)
        """
        if not backups:
            return set(), set()

        retained: Set[Path] = set()

        # Rule 1: Keep N most recent
        if keep_count is not None and keep_count > 0:
            for b in backups[:keep_count]:
                retained.add(b.path)

        # Rule 2: Keep 1 per day for the most recent keep_daily days
        if keep_daily is not None and keep_daily > 0:
            daily_map: Dict[datetime.date, BackupFile] = {}
            for b in backups:
                if b.date not in daily_map:
                    daily_map[b.date] = b
            sorted_dates = sorted(daily_map.keys(), reverse=True)[:keep_daily]
            for d in sorted_dates:
                retained.add(daily_map[d].path)

        # Rule 3: Keep 1 per week for the most recent keep_weekly weeks
        if keep_weekly is not None and keep_weekly > 0:
            weekly_map: Dict[Tuple[int, int], BackupFile] = {}
            for b in backups:
                if b.year_week not in weekly_map:
                    weekly_map[b.year_week] = b
            sorted_weeks = sorted(weekly_map.keys(), reverse=True)[:keep_weekly]
            for w in sorted_weeks:
                retained.add(weekly_map[w].path)

        # Default fallback if no policies specified: keep all
        if keep_count is None and keep_daily is None and keep_weekly is None:
            retained = {b.path for b in backups}

        purged: Set[Path] = {b.path for b in backups} - retained
        return retained, purged

    def execute_rotation(
        self,
        keep_count: Optional[int] = None,
        keep_daily: Optional[int] = None,
        keep_weekly: Optional[int] = None,
        dry_run: bool = False,
        logger: Optional[logging.Logger] = None,
    ) -> Dict[str, List[str]]:
        """Executes rotation policy, returning retained and purged files dict."""
        # pylint: disable=too-many-arguments,too-many-positional-arguments
        # pylint: disable=logging-fstring-interpolation
        if logger is None:
            logger = logging.getLogger("BackupRotationManager")
            logger.setLevel(logging.INFO)

        backups = self.list_backups()
        retained_paths, purged_paths = self.determine_retained_backups(
            backups,
            keep_count=keep_count,
            keep_daily=keep_daily,
            keep_weekly=keep_weekly,
        )

        retained_list = [str(p) for p in sorted(retained_paths)]
        purged_list = [str(p) for p in sorted(purged_paths)]

        logger.info(f"Found {len(backups)} total backups matching '{self.pattern}'.")
        logger.info(f"Retaining {len(retained_list)} backup(s).")
        logger.info(f"Purging {len(purged_list)} backup(s) (Dry Run = {dry_run}).")

        for path in purged_paths:
            if dry_run:
                logger.info(f"[DRY RUN] Would purge: {path}")
            else:
                try:
                    path.unlink()
                    logger.info(f"Purged: {path}")
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error(f"Failed to purge {path}: {e}")

        return {
            "retained": retained_list,
            "purged": purged_list,
        }


def setup_logging(log_file: Optional[str] = None) -> logging.Logger:
    """Sets up standard logger for CLI output and optional log file."""
    logger = logging.getLogger("BackupRotationManager")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(file_handler)

    return logger


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Backup Rotation Manager")
    parser.add_argument(
        "directory", type=str, help="Target directory containing backup files"
    )
    parser.add_argument(
        "--pattern",
        "-p",
        type=str,
        default="*",
        help="Glob pattern to match backup files (default: '*')",
    )
    parser.add_argument(
        "--keep",
        "-k",
        type=int,
        default=None,
        help="Number of most recent backups to retain",
    )
    parser.add_argument(
        "--keep-daily",
        type=int,
        default=None,
        help="Number of recent daily backups to retain",
    )
    parser.add_argument(
        "--keep-weekly",
        type=int,
        default=None,
        help="Number of recent weekly backups to retain",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Simulate execution without deleting any files",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Optional path to log file for writing purge history",
    )
    return parser.parse_args(args)


def main() -> None:
    """Main CLI entry point."""
    args = parse_args()
    logger = setup_logging(args.log_file)
    manager = BackupRotationManager(Path(args.directory), pattern=args.pattern)
    manager.execute_rotation(
        keep_count=args.keep,
        keep_daily=args.keep_daily,
        keep_weekly=args.keep_weekly,
        dry_run=args.dry_run,
        logger=logger,
    )


if __name__ == "__main__":
    main()

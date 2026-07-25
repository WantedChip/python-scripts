"""Directory Watcher Script.

Monitors a directory for file creation, modification, and deletion events
in real time and logs event records with ISO timestamps. Supports extension filtering.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


def setup_logger(log_file: Optional[str] = None) -> logging.Logger:
    """Configure logger for stdout and optional log file."""
    logger = logging.getLogger("directory_watcher")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def matches_extension(filename: str, extensions: Optional[List[str]]) -> bool:
    """Check whether a filename matches specified extensions (case-insensitive)."""
    if not extensions:
        return True
    exts = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions]
    return Path(filename).suffix.lower() in exts


class PollingDirectoryWatcher:
    """Fallback directory watcher using periodic filesystem snapshot polling."""

    def __init__(
        self,
        directory: str,
        extensions: Optional[List[str]] = None,
        callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.directory = os.path.abspath(directory)
        self.extensions = extensions
        self.callback = callback or (lambda event, path: None)
        self.snapshot: Dict[str, float] = {}

    def get_file_state(self) -> Dict[str, float]:
        """Scans directory and returns mapping of relative file paths to mtime."""
        state = {}
        for root, _, files in os.walk(self.directory):
            for file in files:
                if matches_extension(file, self.extensions):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.directory)
                    try:
                        state[rel_path] = os.path.getmtime(full_path)
                    except OSError:
                        pass
        return state

    def poll_once(self) -> List[Tuple[str, str]]:
        """Performs a single snapshot check and returns list of (event_type, path)."""
        current_state = self.get_file_state()
        events = []

        # Detect created & modified
        for path, mtime in current_state.items():
            if path not in self.snapshot:
                events.append(("CREATED", path))
                self.callback("CREATED", path)
            elif mtime > self.snapshot[path]:
                events.append(("MODIFIED", path))
                self.callback("MODIFIED", path)

        # Detect deleted
        for path in self.snapshot:
            if path not in current_state:
                events.append(("DELETED", path))
                self.callback("DELETED", path)

        self.snapshot = current_state
        return events

    def start(self, interval: float = 1.0, duration: Optional[float] = None) -> None:
        """Starts polling loop."""
        self.snapshot = self.get_file_state()
        start_time = time.time()
        while True:
            time.sleep(interval)
            self.poll_once()
            if duration and (time.time() - start_time) >= duration:
                break


if HAS_WATCHDOG:

    class WatchdogHandler(FileSystemEventHandler):
        """Watchdog handler for directory monitoring."""

        def __init__(
            self,
            extensions: Optional[List[str]],
            logger: logging.Logger,
            callback: Optional[Callable[[str, str], None]] = None,
        ) -> None:
            super().__init__()
            self.extensions = extensions
            self.logger = logger
            self.callback = callback or (lambda event, path: None)

        def on_created(self, event: FileSystemEvent) -> None:
            if not event.is_directory and matches_extension(
                event.src_path, self.extensions
            ):
                self.logger.info(
                    f"CREATED: {event.src_path}"
                )  # pylint: disable=logging-fstring-interpolation
                self.callback("CREATED", event.src_path)

        def on_modified(self, event: FileSystemEvent) -> None:
            if not event.is_directory and matches_extension(
                event.src_path, self.extensions
            ):
                self.logger.info(
                    f"MODIFIED: {event.src_path}"
                )  # pylint: disable=logging-fstring-interpolation
                self.callback("MODIFIED", event.src_path)

        def on_deleted(self, event: FileSystemEvent) -> None:
            if not event.is_directory and matches_extension(
                event.src_path, self.extensions
            ):
                self.logger.info(
                    f"DELETED: {event.src_path}"
                )  # pylint: disable=logging-fstring-interpolation
                self.callback("DELETED", event.src_path)


def watch_directory(
    path: str,
    extensions: Optional[List[str]] = None,
    log_file: Optional[str] = None,
    poll_interval: float = 1.0,
    force_polling: bool = False,
    duration: Optional[float] = None,
) -> None:
    """Watches target directory using watchdog if available, else polling."""
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    # pylint: disable=logging-fstring-interpolation
    logger = setup_logger(log_file)
    target_dir = os.path.abspath(path)

    if not os.path.isdir(target_dir):
        logger.error(f"Target path '{target_dir}' is not a valid directory.")
        sys.exit(1)

    logger.info(f"Starting directory watcher on: {target_dir}")
    if extensions:
        logger.info(f"Filtering extensions: {', '.join(extensions)}")

    if HAS_WATCHDOG and not force_polling:
        logger.info("Using watchdog engine.")
        event_handler = WatchdogHandler(extensions, logger)
        observer = Observer()
        observer.schedule(  # type: ignore[no-untyped-call]
            event_handler, target_dir, recursive=True
        )
        observer.start()  # type: ignore[no-untyped-call]
        try:
            start_time = time.time()
            while True:
                time.sleep(poll_interval)
                if duration and (time.time() - start_time) >= duration:
                    break
        except KeyboardInterrupt:
            logger.info("Stopping watcher...")
        finally:
            observer.stop()  # type: ignore[no-untyped-call]
            observer.join()
    else:
        logger.info("Using polling engine.")
        watcher = PollingDirectoryWatcher(
            target_dir,
            extensions,
            callback=lambda evt, file_path: logger.info(f"{evt}: {file_path}"),
        )
        try:
            watcher.start(interval=poll_interval, duration=duration)
        except KeyboardInterrupt:
            logger.info("Stopping watcher...")


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Real-time Directory Event Watcher")
    parser.add_argument("path", help="Directory path to watch")
    parser.add_argument(
        "-e",
        "--extensions",
        nargs="+",
        help="File extensions to filter (e.g. .py .txt)",
    )
    parser.add_argument("-l", "--log-file", help="Path to write event log file")
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=1.0,
        help="Polling/Check interval in seconds",
    )
    parser.add_argument(
        "--polling", action="store_true", help="Force polling engine over watchdog"
    )

    args = parser.parse_args()
    watch_directory(
        args.path,
        extensions=args.extensions,
        log_file=args.log_file,
        poll_interval=args.interval,
        force_polling=args.polling,
    )


if __name__ == "__main__":
    main()

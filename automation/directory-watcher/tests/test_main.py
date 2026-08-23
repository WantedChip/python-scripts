"""Unit tests for Directory Watcher."""

import logging
import os
import tempfile
import time
import unittest
from typing import List, Tuple
from unittest.mock import MagicMock, patch

from main import PollingDirectoryWatcher, WatchdogHandler
from main import main as cli_main
from main import matches_extension, setup_logger, watch_directory


class TestDirectoryWatcher(unittest.TestCase):

    def test_matches_extension(self) -> None:
        self.assertTrue(matches_extension("file.txt", [".txt", ".py"]))
        self.assertTrue(matches_extension("script.PY", ["py"]))
        self.assertFalse(matches_extension("document.pdf", ["txt", "doc"]))
        self.assertTrue(matches_extension("any.file", None))

    def test_polling_watcher_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            events = []

            def on_event(event_type: str, path: str) -> None:
                events.append((event_type, path))

            watcher = PollingDirectoryWatcher(
                tmp_dir, extensions=[".txt"], callback=on_event
            )
            watcher.snapshot = watcher.get_file_state()

            # Create file
            test_file = os.path.join(tmp_dir, "test.txt")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("hello")

            poll_1 = watcher.poll_once()
            self.assertIn(("CREATED", "test.txt"), poll_1)

            # Modify file
            time.sleep(0.05)
            with open(test_file, "a", encoding="utf-8") as f:
                f.write(" world")
            os.utime(test_file, None)  # update mtime explicitly

            poll_2 = watcher.poll_once()
            self.assertIn(("MODIFIED", "test.txt"), poll_2)

            # Delete file
            os.remove(test_file)
            poll_3 = watcher.poll_once()
            self.assertIn(("DELETED", "test.txt"), poll_3)

    def test_setup_logger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "watcher.log")
            logger = setup_logger(log_path)
            logger.info("Test event")
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Test event", content)
            for h in list(logger.handlers):
                h.close()
                logger.removeHandler(h)


class TestPollingDirectoryWatcher(unittest.TestCase):
    """Snapshot polling behaviour of the fallback watcher."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.temp_dir.name

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_get_file_state_ignores_unreadable_files(self) -> None:
        """Files whose mtime cannot be read are skipped silently."""
        target = os.path.join(self.dir_path, "locked.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("data")

        watcher = PollingDirectoryWatcher(self.dir_path, extensions=[".txt"])
        with patch("main.os.path.getmtime", side_effect=OSError("gone")):
            state = watcher.get_file_state()

        self.assertEqual(state, {})

    def test_start_initializes_snapshot_then_loops(self) -> None:
        """start() snapshots first and polls until duration elapses."""
        target = os.path.join(self.dir_path, "seed.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("seed")

        watcher = PollingDirectoryWatcher(self.dir_path, extensions=[".txt"])
        watcher.start(interval=0.01, duration=0.05)

        self.assertIn("seed.txt", watcher.snapshot)

    def test_default_callback_is_noop(self) -> None:
        """A watcher built without a callback exposes a callable."""
        watcher = PollingDirectoryWatcher(self.dir_path)
        self.assertIsNone(watcher.callback("CREATED", "x"))


def _make_handler() -> Tuple[WatchdogHandler, MagicMock, List[Tuple[str, str]]]:
    """Build a WatchdogHandler wired to recording mocks."""
    calls: List[Tuple[str, str]] = []
    logger = MagicMock()

    def record(event_type: str, path: str) -> None:
        calls.append((event_type, path))

    handler = WatchdogHandler([".txt"], logger, callback=record)
    return handler, logger, calls


class TestWatchdogHandler(unittest.TestCase):
    """Synthetic-event tests for the watchdog handler."""

    def test_matching_events_logged_and_forwarded(self) -> None:
        """Matching file events log and invoke the callback."""
        from watchdog.events import (
            FileCreatedEvent,
            FileDeletedEvent,
            FileModifiedEvent,
        )

        handler, logger, calls = _make_handler()

        handler.on_created(FileCreatedEvent(r"C:\watch\note.txt"))
        handler.on_modified(FileModifiedEvent(r"C:\watch\note.txt"))
        handler.on_deleted(FileDeletedEvent(r"C:\watch\note.txt"))

        self.assertEqual(
            calls,
            [
                ("CREATED", r"C:\watch\note.txt"),
                ("MODIFIED", r"C:\watch\note.txt"),
                ("DELETED", r"C:\watch\note.txt"),
            ],
        )
        self.assertEqual(logger.info.call_count, 3)

    def test_non_matching_and_directory_events_ignored(self) -> None:
        """Wrong extensions and directory events never reach callbacks."""
        from watchdog.events import DirCreatedEvent

        handler, logger, calls = _make_handler()

        handler.on_created(DirCreatedEvent(r"C:\watch\subdir"))
        handler.on_modified(DirCreatedEvent(r"C:\watch\subdir"))
        handler.on_deleted(DirCreatedEvent(r"C:\watch\subdir"))
        handler.on_created(DirCreatedEvent(r"C:\watch\photo.jpg"))

        self.assertEqual(calls, [])
        logger.info.assert_not_called()


class TestWatchDirectory(unittest.TestCase):
    """Engine selection and error handling of watch_directory."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.temp_dir.name

    def tearDown(self) -> None:
        watcher_logger = logging.getLogger("directory_watcher")
        for handler in list(watcher_logger.handlers):
            handler.close()
            watcher_logger.removeHandler(handler)
        self.temp_dir.cleanup()

    def test_invalid_directory_exits(self) -> None:
        """A nonexistent target logs an error and exits with status 1."""
        logger = MagicMock()
        with patch("main.setup_logger", return_value=logger):
            with self.assertRaises(SystemExit) as ctx:
                watch_directory(os.path.join(self.dir_path, "nope"))
        self.assertEqual(ctx.exception.code, 1)
        logger.error.assert_called_once()

    def test_polling_engine_runs_for_duration(self) -> None:
        """force_polling uses the polling loop and stops after duration."""
        seed = os.path.join(self.dir_path, "a.txt")
        with open(seed, "w", encoding="utf-8") as f:
            f.write("x")

        watch_directory(
            self.dir_path,
            extensions=[".txt"],
            force_polling=True,
            duration=0.1,
        )
        # Reaching this point means the polling loop terminated cleanly.

    @patch("main.Observer")
    @patch("main.time.sleep", side_effect=KeyboardInterrupt)
    def test_watchdog_engine_stops_observer_on_interrupt(
        self, mock_sleep: MagicMock, mock_observer_cls: MagicMock
    ) -> None:
        """KeyboardInterrupt during watching still stops the observer."""
        logger = setup_logger(None)
        observer = mock_observer_cls.return_value

        with patch("main.setup_logger", return_value=logger):
            watch_directory(self.dir_path, poll_interval=0.01)

        observer.schedule.assert_called_once()
        observer.start.assert_called_once()
        observer.stop.assert_called_once()
        observer.join.assert_called_once()
        scheduled_args = observer.schedule.call_args[0]
        self.assertIsInstance(scheduled_args[0], WatchdogHandler)
        self.assertEqual(scheduled_args[1], os.path.abspath(self.dir_path))

    @patch("main.Observer")
    @patch("main.time.sleep", side_effect=KeyboardInterrupt)
    def test_watchdog_engine_logs_engine_choice(
        self, mock_sleep: MagicMock, mock_observer_cls: MagicMock
    ) -> None:
        """The watchdog engine announces itself via log output."""
        logger = MagicMock()

        with patch("main.setup_logger", return_value=logger):
            watch_directory(self.dir_path, extensions=[".py"])

        logger.info.assert_any_call("Using watchdog engine.")
        logger.info.assert_any_call("Filtering extensions: .py")


class TestCliEntrypoint(unittest.TestCase):
    """Argument plumbing from main() into watch_directory."""

    @patch("main.watch_directory")
    def test_main_parses_cli_arguments(self, mock_watch: MagicMock) -> None:
        """CLI flags map onto watch_directory keyword arguments."""
        argv = [
            "directory_watcher.py",
            r"C:\target",
            "-e",
            ".txt",
            ".md",
            "-l",
            "out.log",
            "-i",
            "2.5",
            "--polling",
        ]
        with patch("sys.argv", argv):
            cli_main()
        mock_watch.assert_called_once_with(
            r"C:\target",
            extensions=[".txt", ".md"],
            log_file="out.log",
            poll_interval=2.5,
            force_polling=True,
        )


if __name__ == "__main__":
    unittest.main()

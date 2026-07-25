"""Unit tests for Directory Watcher."""

import os
import tempfile
import time
import unittest

from main import PollingDirectoryWatcher, matches_extension, setup_logger


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


if __name__ == "__main__":
    unittest.main()

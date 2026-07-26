"""Unit tests for mutation-witness main.py."""

import sys
import tempfile
import unittest
from pathlib import Path

from main import compute_diff, take_snapshot, wrap_command


class TestMutationWitness(unittest.TestCase):
    """Tests for file snapshot, process tree inspection, and command wrapping."""

    def test_snapshot_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test.txt"
            file_path.write_text("line 1\n", encoding="utf-8")

            snap1 = take_snapshot(file_path)

            file_path.write_text("line 1\nline 2\n", encoding="utf-8")
            snap2 = take_snapshot(file_path)

            action, delta, diff = compute_diff(snap1, snap2)
            self.assertEqual(action, "MODIFIED")
            self.assertGreater(delta, 0)
            self.assertIn("line 2", diff)

    def test_wrap_command_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_file = Path(tmp_dir) / "output.txt"
            log_file = Path(tmp_dir) / "log.json"

            # Wrapped python inline command to append text
            cmd = [
                sys.executable,
                "-c",
                f"open(r'{target_file}', 'w').write('created content')",
            ]

            event = wrap_command(target_file, cmd, log_output=log_file)
            self.assertIsNotNone(event)
            if event:
                self.assertEqual(event.action, "CREATED")
                self.assertIn("created content", event.diff)
                self.assertTrue(log_file.exists())


if __name__ == "__main__":
    unittest.main()

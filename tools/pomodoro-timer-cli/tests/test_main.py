"""
Unit tests for Pomodoro Timer CLI.
"""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from main import SessionManager, build_parser, format_progress_bar, main, run_timer


class TestPomodoroTimer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.history_file = self.temp_dir / "test_history.json"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_format_progress_bar(self):
        bar_50 = format_progress_bar(30, 60, length=20)
        self.assertIn("50.0%", bar_50)
        self.assertIn("00:30 / 01:00", bar_50)
        self.assertIn("█" * 10, bar_50)

    def test_session_manager(self):
        manager = SessionManager(self.history_file)
        self.assertEqual(manager.load_history(), [])

        manager.record_session("work", 25.0, completed=True)
        manager.record_session("break", 5.0, completed=True)
        manager.record_session("work", 25.0, completed=False)

        stats = manager.get_stats()
        self.assertEqual(stats["total_sessions"], 3)
        self.assertEqual(stats["completed_work_sessions"], 1)
        self.assertEqual(stats["completed_break_sessions"], 1)
        self.assertEqual(stats["total_work_minutes"], 25.0)

    def test_run_timer_test_mode(self):
        completed = run_timer(
            duration_seconds=2,
            label="TestWork",
            tick_delay=0.001,
            notify_beep=False,
        )
        self.assertTrue(completed)


class TestProgressBarEdgeCases(unittest.TestCase):
    """Test suite for progress bar math edge cases."""

    def test_zero_total_counts_as_complete(self) -> None:
        bar = format_progress_bar(0, 0, length=10)
        self.assertIn("100.0%", bar)
        self.assertEqual(bar.count("█"), 10)

    def test_elapsed_beyond_total_is_clamped(self) -> None:
        bar = format_progress_bar(120, 60, length=4)
        self.assertIn("100.0%", bar)
        self.assertIn("02:00 / 01:00", bar)


class TestSessionManagerEdgeCases(unittest.TestCase):
    """Test suite for history persistence robustness."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

    def test_corrupt_history_returns_empty(self) -> None:
        hist_file = self.temp_dir / "broken.json"
        hist_file.write_text("{definitely not json", encoding="utf-8")
        manager = SessionManager(hist_file)
        self.assertEqual(manager.load_history(), [])

    def test_non_list_history_returns_empty(self) -> None:
        hist_file = self.temp_dir / "object.json"
        hist_file.write_text('{"sessions": 3}', encoding="utf-8")
        manager = SessionManager(hist_file)
        self.assertEqual(manager.load_history(), [])

    def test_record_creates_missing_parent_folders(self) -> None:
        nested = self.temp_dir / "deep" / "path" / "hist.json"
        manager = SessionManager(nested)
        entry: Dict[str, Any] = manager.record_session("work", 25.0, True)
        self.assertTrue(nested.exists())
        self.assertEqual(entry["type"], "work")

    def test_break_minutes_are_tracked_separately(self) -> None:
        hist_file = self.temp_dir / "hist.json"
        manager = SessionManager(hist_file)
        manager.record_session("break", 5.0, True)
        stats = manager.get_stats()
        self.assertEqual(stats["total_break_minutes"], 5.0)
        self.assertEqual(stats["completed_break_sessions"], 1.0)


class TestRunTimerInterruption(unittest.TestCase):
    """Test suite for timer interruption and notification behavior."""

    def test_keyboard_interrupt_returns_false(self) -> None:
        with patch("main.time.sleep", side_effect=KeyboardInterrupt):
            completed = run_timer(duration_seconds=5, label="Work")
        self.assertFalse(completed)

    def test_beep_written_on_completion(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            completed = run_timer(
                duration_seconds=1,
                label="Beeped",
                tick_delay=0.001,
                notify_beep=True,
            )
        self.assertTrue(completed)
        self.assertIn("\a", buf.getvalue())


class TestPomodoroCli(unittest.TestCase):
    """End-to-end tests for build_parser and the main() entry point."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.history = self.temp_dir / "hist.json"

    def test_build_parser_start_and_stats_flags(self) -> None:
        parser = build_parser()
        start_args = parser.parse_args(
            [
                "start",
                "-w",
                "30",
                "-b",
                "7",
                "-c",
                "2",
                "--history-file",
                str(self.history),
                "--test-mode",
            ]
        )
        self.assertEqual(start_args.command, "start")
        self.assertEqual(start_args.work, 30.0)
        self.assertEqual(start_args.break_time, 7.0)
        self.assertEqual(start_args.cycles, 2)
        self.assertTrue(start_args.test_mode)

        stats_args = parser.parse_args(["stats"])
        self.assertEqual(stats_args.command, "stats")

    def test_main_stats_reports_aggregates(self) -> None:
        manager = SessionManager(self.history)
        manager.record_session("work", 25.0, True)
        manager.record_session("work", 10.0, False)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["stats", "--history-file", str(self.history)])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("Total Logged Sessions:       2", out)
        self.assertIn("Completed Work Sessions:     1", out)
        self.assertIn("Total Work Time:             25.0 minutes", out)

    def test_main_default_command_is_stats(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([])
        self.assertEqual(rc, 0)
        self.assertIn("=== Pomodoro Session Stats ===", buf.getvalue())

    def test_main_start_records_all_cycle_sessions(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(
                [
                    "start",
                    "-w",
                    "0",
                    "-b",
                    "0",
                    "-c",
                    "2",
                    "--history-file",
                    str(self.history),
                    "--test-mode",
                ]
            )
        self.assertEqual(rc, 0)
        stored: List[Dict[str, Any]] = json.loads(
            self.history.read_text(encoding="utf-8")
        )
        types = [entry["type"] for entry in stored]
        # Two work sessions and one inter-cycle break.
        self.assertEqual(types, ["work", "break", "work"])
        self.assertTrue(all(entry["completed"] for entry in stored))

    def test_main_start_stops_when_work_interrupted(self) -> None:
        with patch("main.run_timer", return_value=False):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(
                    [
                        "start",
                        "--history-file",
                        str(self.history),
                        "--test-mode",
                    ]
                )
        self.assertEqual(rc, 0)
        self.assertIn("Stopping Pomodoro routine.", buf.getvalue())
        stored: List[Dict[str, Any]] = json.loads(
            self.history.read_text(encoding="utf-8")
        )
        self.assertFalse(stored[0]["completed"])


if __name__ == "__main__":
    unittest.main()

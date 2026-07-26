"""
Unit tests for Pomodoro Timer CLI.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from main import SessionManager, format_progress_bar, run_timer


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


if __name__ == "__main__":
    unittest.main()

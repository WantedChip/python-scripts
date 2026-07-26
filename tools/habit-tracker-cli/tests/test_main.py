"""Unit tests for Habit Tracker CLI."""

import os
import tempfile
import unittest
from datetime import date, timedelta

from main import HabitTracker


class TestHabitTracker(unittest.TestCase):
    """Test suite for HabitTracker SQLite logic and streak computations."""

    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.tracker = HabitTracker(db_path=self.temp_db.name)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_add_and_list_habits(self) -> None:
        hid = self.tracker.add_habit("Read Books", "Read 20 pages daily")
        self.assertIsNotNone(hid)
        habits = self.tracker.list_habits()
        self.assertEqual(len(habits), 1)
        self.assertEqual(habits[0]["name"], "Read Books")

    def test_checkin_and_uncheckin(self) -> None:
        self.tracker.add_habit("Meditation")
        today_str = date.today().isoformat()
        res1 = self.tracker.checkin("Meditation", today_str)
        self.assertTrue(res1)
        res_dup = self.tracker.checkin("Meditation", today_str)
        self.assertFalse(res_dup)

        uncheck_res = self.tracker.uncheckin("Meditation", today_str)
        self.assertTrue(uncheck_res)

    def test_streak_calculation(self) -> None:
        self.tracker.add_habit("Workout")
        today = date.today()
        # Checkin for past 3 consecutive days including today
        for i in range(3):
            d_str = (today - timedelta(days=i)).isoformat()
            self.tracker.checkin("Workout", d_str)

        stats = self.tracker.calculate_streaks("Workout")
        self.assertEqual(stats["current_streak"], 3)
        self.assertEqual(stats["longest_streak"], 3)
        self.assertEqual(stats["total_checkins"], 3)

    def test_calendar_rendering(self) -> None:
        self.tracker.add_habit("Code")
        self.tracker.checkin("Code", "2026-07-15")
        cal_str = self.tracker.render_calendar("Code", 2026, 7)
        self.assertIn("CODE - July 2026", cal_str)
        self.assertIn("[X]", cal_str)

    def test_delete_habit(self) -> None:
        self.tracker.add_habit("Run")
        self.assertTrue(self.tracker.delete_habit("Run"))
        self.assertEqual(len(self.tracker.list_habits()), 0)


if __name__ == "__main__":
    unittest.main()

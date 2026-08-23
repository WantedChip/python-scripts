"""Unit tests for Habit Tracker CLI."""

import io
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta

from main import HabitTracker, build_parser, main


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


class TestTrackerEdgeCases(unittest.TestCase):
    """Error paths, gap handling, weekly table, and calendar details."""

    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.tracker = HabitTracker(db_path=self.temp_db.name)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_checkin_unknown_habit_raises_value_error(self) -> None:
        """Checking in a habit that does not exist raises ValueError."""
        with self.assertRaises(ValueError):
            self.tracker.checkin("Ghost Habit")

    def test_uncheckin_unknown_habit_raises_value_error(self) -> None:
        """Unchecking an unknown habit or date reports no-op outcomes."""
        with self.assertRaises(ValueError):
            self.tracker.uncheckin("Ghost Habit")

        self.tracker.add_habit("Real Habit")
        self.assertFalse(self.tracker.uncheckin("Real Habit", "2030-01-01"))

    def test_delete_missing_habit_returns_false(self) -> None:
        """Deleting a nonexistent habit returns False."""
        self.assertFalse(self.tracker.delete_habit("Never Added"))

    def test_stats_for_empty_history_are_zeroed(self) -> None:
        """A habit with no check-ins reports zero streaks."""
        self.tracker.add_habit("Empty")
        stats = self.tracker.calculate_streaks("Empty")
        self.assertEqual(stats["current_streak"], 0)
        self.assertEqual(stats["longest_streak"], 0)
        self.assertEqual(stats["total_checkins"], 0)

    def test_current_streak_counts_from_yesterday(self) -> None:
        """A streak anchored on yesterday still counts when today is open."""
        self.tracker.add_habit("Stretch")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        two_days_ago = (date.today() - timedelta(days=2)).isoformat()
        self.tracker.checkin("Stretch", yesterday)
        self.tracker.checkin("Stretch", two_days_ago)

        stats = self.tracker.calculate_streaks("Stretch")
        self.assertEqual(stats["current_streak"], 2)
        self.assertEqual(stats["longest_streak"], 2)

    def test_longest_streak_ignores_non_consecutive_gap(self) -> None:
        """Separated check-ins do not merge into one long streak."""
        self.tracker.add_habit("Gap Habit")
        today = date.today()
        self.tracker.checkin("Gap Habit", today.isoformat())
        self.tracker.checkin("Gap Habit", (today - timedelta(days=5)).isoformat())

        stats = self.tracker.calculate_streaks("Gap Habit")
        self.assertEqual(stats["current_streak"], 1)
        self.assertEqual(stats["longest_streak"], 1)
        self.assertEqual(stats["total_checkins"], 2)

    def test_render_calendar_leaves_padding_cells_blank(self) -> None:
        """Calendar grid renders checked days and blank leading padding."""
        self.tracker.add_habit("Journal")
        self.tracker.checkin("Journal", "2024-01-15")
        rendered = self.tracker.render_calendar("Journal", 2024, 1)

        self.assertIn("--- JOURNAL - January 2024 ---", rendered)
        self.assertIn("[X]", rendered)
        self.assertIn("Mo  Tu  We  Th  Fr  Sa  Su", rendered)

    def test_weekly_table_without_habits(self) -> None:
        """An empty tracker renders the 'no habits' placeholder."""
        self.assertEqual(self.tracker.render_weekly_table(), "No habits configured.")

    def test_weekly_table_marks_recent_checkin(self) -> None:
        """The weekly table shows rows per habit with streak column."""
        self.tracker.add_habit("Walk")
        self.tracker.checkin("Walk", date.today().isoformat())

        table = self.tracker.render_weekly_table()
        first_line = table.splitlines()[0]
        self.assertIn("HABIT", first_line)
        self.assertIn("STREAK", first_line)
        self.assertIn("Walk", table)
        self.assertIn("[X]", table)


class TestCommandLine(unittest.TestCase):
    """End-to-end subcommand execution against a temporary database."""

    def setUp(self) -> None:
        self.work_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.work_dir, True)
        original_cwd = os.getcwd()
        self.addCleanup(os.chdir, original_cwd)
        os.chdir(self.work_dir)

    def _run(self, *args: str) -> tuple:
        """Run the CLI with captured stdout, returning (code, output)."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(list(args))
        return code, buf.getvalue()

    def test_build_parser_defaults(self) -> None:
        """Subparser flags expose their documented defaults."""
        parsed = build_parser().parse_args(["add", "x"])
        self.assertEqual(parsed.description, "")

        parsed_cal = build_parser().parse_args(["calendar", "x"])
        self.assertEqual(parsed_cal.month, date.today().month)
        self.assertEqual(parsed_cal.year, date.today().year)

    def test_full_checkin_lifecycle_via_cli(self) -> None:
        """Add, duplicate-add, list, check-in twice, uncheck twice."""
        code, out = self._run("add", "hydrate", "--description", "water")
        self.assertEqual(code, 0)
        self.assertIn("Created habit 'hydrate'", out)

        code, out = self._run("add", "hydrate")
        self.assertIn("already exists", out)

        code, out = self._run("list")
        self.assertIn("[1] hydrate - water", out)

        code, out = self._run("checkin", "hydrate")
        self.assertIn("Checked in 'hydrate'", out)

        code, out = self._run("checkin", "hydrate")
        self.assertIn("Already checked in", out)

        code, out = self._run("uncheck", "hydrate")
        self.assertIn("Removed checkin", out)

        code, out = self._run("uncheck", "hydrate")
        self.assertIn("No checkin found to remove.", out)

    def test_stats_calendar_weekly_and_delete_subcommands(self) -> None:
        """stats, calendar, weekly, and delete all execute successfully."""
        self._run("add", "read")
        self._run("checkin", "read")

        code, out = self._run("stats", "read")
        self.assertEqual(code, 0)
        self.assertIn("Habit: read", out)
        self.assertIn("Current Streak: 1 days", out)

        code, out = self._run("stats")
        self.assertIn("Habit: read", out)

        code, out = self._run("calendar", "read", "--month", "1", "--year", "2024")
        self.assertIn("READ - January 2024", out)

        code, out = self._run("weekly")
        self.assertIn("read", out)

        code, out = self._run("delete", "read")
        self.assertIn("Deleted habit 'read'.", out)

        code, out = self._run("delete", "read")
        self.assertIn("not found", out)

    def test_bare_invocation_prints_help(self) -> None:
        """Running without a subcommand prints help and exits 0."""
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("usage:", out)

    def test_duplicate_add_is_reported_not_raised(self) -> None:
        """Adding an existing habit hits the IntegrityError branch."""
        self._run("add", "dupe")
        db = HabitTracker(os.path.join(self.work_dir, "habits.db"))
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_habit("dupe")

        code, out = self._run("add", "dupe")
        self.assertIn("already exists", out)


if __name__ == "__main__":
    unittest.main()

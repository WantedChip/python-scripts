"""Terminal Habit Tracker CLI.

Manages habits, daily check-ins, streak calculation, completion metrics,
and ASCII calendar / summary tables using SQLite storage.
"""

from __future__ import annotations

import argparse
import calendar
import sqlite3
import sys
from contextlib import closing
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods


DEFAULT_DB_PATH = "habits.db"


class HabitTracker:
    """Manager for habit tracking data and statistics."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        """Initialize tracker database.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with closing(self._get_conn()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_at DATE DEFAULT CURRENT_DATE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER NOT NULL,
                    checkin_date DATE NOT NULL,
                    FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE,
                    UNIQUE(habit_id, checkin_date)
                )
                """
            )
            conn.commit()

    def add_habit(self, name: str, description: str = "") -> int:
        """Create a new habit.

        Args:
            name: Habit title.
            description: Optional details.

        Returns:
            Inserted habit ID.
        """
        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO habits (name, description) VALUES (?, ?)",
                (name, description),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def list_habits(self) -> List[Dict[str, Any]]:
        """List all tracked habits."""
        with closing(self._get_conn()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM habits ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def delete_habit(self, name: str) -> bool:
        """Delete a habit by name."""
        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM habits WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

    def checkin(self, name: str, date_str: Optional[str] = None) -> bool:
        """Record a check-in for a habit.

        Args:
            name: Habit name.
            date_str: ISO date 'YYYY-MM-DD'. Defaults to today.

        Returns:
            True if checked in, False if already checked in or habit not found.
        """
        target_date = date_str or date.today().isoformat()
        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM habits WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Habit '{name}' not found.")
            habit_id = row[0]

            try:
                cursor.execute(
                    "INSERT INTO checkins (habit_id, checkin_date) VALUES (?, ?)",
                    (habit_id, target_date),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def uncheckin(self, name: str, date_str: Optional[str] = None) -> bool:
        """Remove a check-in for a habit."""
        target_date = date_str or date.today().isoformat()
        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM habits WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Habit '{name}' not found.")
            habit_id = row[0]

            cursor.execute(
                "DELETE FROM checkins WHERE habit_id = ? AND checkin_date = ?",
                (habit_id, target_date),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_checkin_dates(self, habit_name: str) -> List[date]:
        """Fetch all check-in dates for a habit sorted chronologically."""
        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT checkin_date FROM checkins c
                JOIN habits h ON c.habit_id = h.id
                WHERE h.name = ?
                ORDER BY checkin_date ASC
                """,
                (habit_name,),
            )
            rows = cursor.fetchall()
            return [datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows]

    def calculate_streaks(self, habit_name: str) -> Dict[str, Any]:
        """Compute current and longest consecutive streak stats for a habit.

        Args:
            habit_name: Name of habit.

        Returns:
            Dictionary containing current_streak, longest_streak, total_checkins.
        """
        checkin_dates = self.get_checkin_dates(habit_name)
        if not checkin_dates:
            return {"current_streak": 0, "longest_streak": 0, "total_checkins": 0}

        dates_set = set(checkin_dates)

        # Calculate current streak ending today or yesterday
        today = date.today()
        current_streak = 0
        curr_day = today
        if curr_day not in dates_set:
            curr_day = today - timedelta(days=1)

        while curr_day in dates_set:
            current_streak += 1
            curr_day -= timedelta(days=1)

        # Calculate longest streak
        longest_streak = 0
        sorted_dates = sorted(list(dates_set))
        if sorted_dates:
            temp_streak = 1
            longest_streak = 1
            for i in range(1, len(sorted_dates)):
                if sorted_dates[i] == sorted_dates[i - 1] + timedelta(days=1):
                    temp_streak += 1
                else:
                    temp_streak = 1
                longest_streak = max(longest_streak, temp_streak)

        return {
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "total_checkins": len(dates_set),
        }

    def render_calendar(self, habit_name: str, year: int, month: int) -> str:
        """Generate ASCII month calendar showing check-in status.

        Args:
            habit_name: Target habit.
            year: Year integer.
            month: Month integer (1-12).

        Returns:
            Formatted ASCII calendar grid string.
        """
        checkin_dates = set(self.get_checkin_dates(habit_name))
        cal = calendar.monthcalendar(year, month)
        month_name = calendar.month_name[month]

        output = [f"--- {habit_name.upper()} - {month_name} {year} ---"]
        output.append("Mo  Tu  We  Th  Fr  Sa  Su")

        for week in cal:
            week_str = []
            for day in week:
                if day == 0:
                    week_str.append("    ")
                else:
                    d_obj = date(year, month, day)
                    mark = "[X]" if d_obj in checkin_dates else f"{day:2d} "
                    week_str.append(mark)
            output.append(" ".join(week_str))

        return "\n".join(output)

    def render_weekly_table(self) -> str:
        """Render weekly summary table for all habits over past 7 days."""
        habits = self.list_habits()
        if not habits:
            return "No habits configured."

        today = date.today()
        past_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]

        header_days = " ".join([d.strftime("%a") for d in past_7_days])
        lines = [f"{'HABIT':<20} | {header_days} | STREAK"]
        lines.append("-" * (23 + len(header_days) + 10))

        for h in habits:
            name = h["name"]
            dates = set(self.get_checkin_dates(name))
            row_marks = " ".join(
                [" [X]" if d in dates else " [ ]" for d in past_7_days]
            )
            streaks = self.calculate_streaks(name)
            curr = streaks["current_streak"]
            lines.append(f"{name:<20} |{row_marks} | {curr} days")

        return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Terminal Habit Tracker CLI")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    add_parser = subparsers.add_parser("add", help="Add a new habit")
    add_parser.add_argument("name", help="Habit name")
    add_parser.add_argument("--description", default="", help="Habit description")

    subparsers.add_parser("list", help="List all habits")

    check_parser = subparsers.add_parser("checkin", help="Check in a habit")
    check_parser.add_argument("name", help="Habit name")
    check_parser.add_argument("--date", help="ISO Date YYYY-MM-DD (defaults to today)")

    uncheck_parser = subparsers.add_parser("uncheck", help="Un-check in a habit")
    uncheck_parser.add_argument("name", help="Habit name")
    uncheck_parser.add_argument("--date", help="ISO Date YYYY-MM-DD")

    stats_parser = subparsers.add_parser("stats", help="Display streaks & stats")
    stats_parser.add_argument("name", nargs="?", help="Optional specific habit name")

    cal_parser = subparsers.add_parser("calendar", help="Display ASCII month calendar")
    cal_parser.add_argument("name", help="Habit name")
    cal_parser.add_argument(
        "--month",
        type=int,
        default=date.today().month,
        help="Month (1-12)",
    )
    cal_parser.add_argument(
        "--year",
        type=int,
        default=date.today().year,
        help="Year (e.g. 2026)",
    )

    subparsers.add_parser("weekly", help="Display weekly summary table")

    del_parser = subparsers.add_parser("delete", help="Delete a habit")
    del_parser.add_argument("name", help="Habit name to delete")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for Habit Tracker CLI."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    tracker = HabitTracker()

    if parsed.command == "add":
        try:
            hid = tracker.add_habit(parsed.name, parsed.description)
            print(f"Created habit '{parsed.name}' (ID: {hid})")
        except sqlite3.IntegrityError:
            print(f"Habit '{parsed.name}' already exists.")
    elif parsed.command == "list":
        habits = tracker.list_habits()
        for h in habits:
            print(f"[{h['id']}] {h['name']} - {h['description']}")
    elif parsed.command == "checkin":
        res = tracker.checkin(parsed.name, parsed.date)
        if res:
            d_str = parsed.date or date.today().isoformat()
            print(f"Checked in '{parsed.name}' for {d_str}!")
        else:
            print(f"Already checked in '{parsed.name}' for that date.")
    elif parsed.command == "uncheck":
        res = tracker.uncheckin(parsed.name, parsed.date)
        if res:
            print(f"Removed checkin for '{parsed.name}'.")
        else:
            print("No checkin found to remove.")
    elif parsed.command == "stats":
        habits_list: List[str] = (
            [parsed.name]
            if parsed.name
            else [str(h["name"]) for h in tracker.list_habits()]
        )
        for name in habits_list:
            s = tracker.calculate_streaks(name)
            print(f"Habit: {name}")
            print(f"  Current Streak: {s['current_streak']} days")
            print(f"  Longest Streak: {s['longest_streak']} days")
            print(f"  Total Checkins: {s['total_checkins']}")
    elif parsed.command == "calendar":
        print(tracker.render_calendar(parsed.name, parsed.year, parsed.month))
    elif parsed.command == "weekly":
        print(tracker.render_weekly_table())
    elif parsed.command == "delete":
        if tracker.delete_habit(parsed.name):
            print(f"Deleted habit '{parsed.name}'.")
        else:
            print(f"Habit '{parsed.name}' not found.")
    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())

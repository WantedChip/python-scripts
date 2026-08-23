"""
Unit tests for Task Time Tracker CLI
"""

import contextlib
import csv
import io
import json
import os
import runpy
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest import mock

from main import TimeSession, TimeTrackerManager, build_parser, format_duration, main


class TestTimeTrackerHelpers(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(3665), "01:01:05")
        self.assertEqual(format_duration(0), "00:00:00")
        self.assertEqual(format_duration(59), "00:00:59")

    def test_format_duration_rounds_fractional_seconds(self) -> None:
        """Sub-second values round to the nearest whole second."""
        self.assertEqual(format_duration(59.7), "00:01:00")
        self.assertEqual(format_duration(125.2), "00:02:05")


class TestTimeSession(unittest.TestCase):
    def test_session_lifecycle(self) -> None:
        s = TimeSession(1, "Coding", "Dev")
        self.assertTrue(s.is_active())
        self.assertIsNone(s.end_time)

        s.stop()
        self.assertFalse(s.is_active())
        self.assertIsNotNone(s.end_time)
        self.assertGreaterEqual(s.duration_seconds, 0)

    def test_dict_round_trip_preserves_fields(self) -> None:
        """to_dict/from_dict restore every field including defaults."""
        original = TimeSession(
            id=3,
            task="Refactor",
            project="Backend",
            start_time="2026-08-01T08:00:00",
            end_time="2026-08-01T09:30:00",
            duration_seconds=5400.0,
        )
        clone = TimeSession.from_dict(original.to_dict())
        self.assertEqual(clone.id, 3)
        self.assertEqual(clone.task, "Refactor")
        self.assertEqual(clone.project, "Backend")
        self.assertEqual(clone.duration_seconds, 5400.0)
        self.assertFalse(clone.is_active())

    def test_from_dict_applies_defaults(self) -> None:
        """Missing optional keys fall back to documented defaults."""
        minimal: Dict[str, Any] = {"id": 9, "task": "Sparse"}
        s = TimeSession.from_dict(minimal)
        self.assertEqual(s.project, "General")
        self.assertIsNone(s.end_time)
        self.assertEqual(s.duration_seconds, 0.0)

    def test_active_session_duration_grows_from_start(self) -> None:
        """An active session reports elapsed time since its start."""
        started = datetime.now() - timedelta(seconds=45)
        s = TimeSession(id=1, task="live", start_time=started.isoformat())
        self.assertGreaterEqual(s.calculate_duration(), 44.0)
        self.assertGreaterEqual(s.get_duration(), 44.0)

    def test_stop_is_idempotent(self) -> None:
        """Stopping an already stopped session changes nothing."""
        s = TimeSession(id=1, task="done", end_time="2026-08-01T10:00:00")
        s.stop()
        self.assertEqual(s.end_time, "2026-08-01T10:00:00")


class TestTimeTrackerManager(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = os.path.join(self.temp_dir, "time_tracker.json")
        self.mgr = TimeTrackerManager(self.file_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_start_stop_switch(self) -> None:
        s1 = self.mgr.start_task("Task 1", "Proj A")
        active = self.mgr.get_active()
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.id, s1.id)

        stopped = self.mgr.stop_task()
        self.assertIsNotNone(stopped)
        assert stopped is not None
        self.assertEqual(stopped.id, s1.id)
        self.assertIsNone(self.mgr.get_active())

        st, s2 = self.mgr.switch_task("Task 2", "Proj B")
        self.assertIsNone(st)
        active2 = self.mgr.get_active()
        self.assertIsNotNone(active2)
        assert active2 is not None
        self.assertEqual(active2.id, s2.id)

    def test_report_generation(self) -> None:
        s = self.mgr.start_task("Design UI", "Frontend")
        s.duration_seconds = 3600
        s.stop()
        self.mgr.save()

        rpt = self.mgr.get_report(period="daily")
        self.assertEqual(rpt["session_count"], 1)
        self.assertIn("Frontend", rpt["project_totals"])

    def test_export_csv(self) -> None:
        self.mgr.start_task("Write Tests", "Testing")
        self.mgr.stop_task()
        csv_path = os.path.join(self.temp_dir, "out.csv")
        self.mgr.export_csv(csv_path)
        self.assertTrue(os.path.exists(csv_path))

    def test_corrupt_storage_loads_as_empty(self) -> None:
        """Unparseable storage files degrade to an empty tracker."""
        with open(self.file_path, "w", encoding="utf-8") as handle:
            handle.write("{broken json[")
        fresh = TimeTrackerManager(self.file_path)
        self.assertEqual(fresh.sessions, [])
        self.assertIsNone(fresh.get_active())

    def test_ids_increment_beyond_existing_maximum(self) -> None:
        """New ids continue after the highest stored id."""
        old = TimeSession.from_dict(
            {"id": 7, "task": "historic", "end_time": "2026-08-01T10:00:00"}
        )
        self.mgr.sessions.append(old)
        new_id = self.mgr.start_task("next").id
        self.assertEqual(new_id, 8)

    def test_starting_new_task_stops_running_one(self) -> None:
        """start_task implicitly closes any previously running timer."""
        first = self.mgr.start_task("first")
        second = self.mgr.start_task("second")
        self.assertFalse(first.is_active())
        self.assertTrue(second.is_active())
        stopped, _ = self.mgr.switch_task("third")
        self.assertIsNotNone(stopped)
        self.assertEqual(stopped.task if stopped else "", "second")

    def test_stop_without_active_returns_none(self) -> None:
        """Stopping with no active session is a safe no-op."""
        self.assertIsNone(self.mgr.stop_task())


class TestReportingPeriodsAndFilters(unittest.TestCase):
    """Aggregation behavior across periods and project filters."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = os.path.join(self.temp_dir, "time_tracker.json")
        self.mgr = TimeTrackerManager(self.file_path)
        # Anchor fixture timestamps to noon today so daily/weekly windows
        # stay deterministic even when the suite runs shortly after midnight
        # (a raw now - 2h start would land on yesterday and vanish from the
        # daily report).
        now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)

        today = TimeSession.from_dict(
            {
                "id": 1,
                "task": "today work",
                "project": "Alpha",
                "start_time": (now - timedelta(hours=2)).isoformat(),
                "end_time": now.isoformat(),
                "duration_seconds": 7200.0,
            }
        )
        ancient = TimeSession.from_dict(
            {
                "id": 2,
                "task": "old work",
                "project": "Beta",
                "start_time": (now - timedelta(days=10)).isoformat(),
                "end_time": (now - timedelta(days=10, hours=-1)).isoformat(),
                "duration_seconds": 3600.0,
            }
        )
        other_project = TimeSession.from_dict(
            {
                "id": 3,
                "task": "beta today",
                "project": "Beta",
                "start_time": (now - timedelta(hours=1)).isoformat(),
                "end_time": now.isoformat(),
                "duration_seconds": 1800.0,
            }
        )
        self.mgr.sessions = [today, ancient, other_project]

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_daily_report_excludes_old_sessions(self) -> None:
        """Daily aggregation only counts sessions started today."""
        rpt = self.mgr.get_report(period="daily")
        self.assertEqual(rpt["session_count"], 2)
        self.assertAlmostEqual(rpt["total_seconds"], 9000.0)
        self.assertIn("Alpha", rpt["project_totals"])
        self.assertIn("Beta", rpt["project_totals"])

    def test_weekly_report_includes_recent_only(self) -> None:
        """Weekly windows include this week's sessions and skip older ones."""
        rpt = self.mgr.get_report(period="weekly")
        self.assertEqual(rpt["session_count"], 2)
        self.assertNotIn("old work", rpt["task_totals"])

    def test_all_period_covers_everything(self) -> None:
        """'all' sums every stored session regardless of age."""
        rpt = self.mgr.get_report(period="all")
        self.assertEqual(rpt["session_count"], 3)
        self.assertAlmostEqual(rpt["total_seconds"], 12600.0)

    def test_project_filter_is_case_insensitive(self) -> None:
        """Project filters ignore case when matching."""
        rpt = self.mgr.get_report(period="all", project_filter="alpha")
        self.assertEqual(rpt["session_count"], 1)
        self.assertAlmostEqual(rpt["total_seconds"], 7200.0)
        self.assertIn("Alpha: today work", rpt["task_totals"])


class TestCsvExportContent(unittest.TestCase):
    """CSV export formatting details."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.manager = TimeTrackerManager(os.path.join(self.temp_dir, "db.json"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_rows_include_headers_and_active_marker(self) -> None:
        """Exported CSV has headers, durations, and ACTIVE placeholders."""
        done = self.manager.start_task("finished task", "Ops")
        done.stop()
        done.duration_seconds = 90.0
        self.manager.start_task("running task", "Ops")  # left active

        out_path = os.path.join(self.temp_dir, "export.csv")
        self.manager.export_csv(out_path)
        with open(out_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0][:4], ["ID", "Task", "Project", "Start Time"])
        self.assertEqual(rows[1][4], done.end_time)
        self.assertEqual(rows[1][6], "00:01:30")
        self.assertEqual(rows[2][4], "ACTIVE")
        self.assertEqual(rows[2][6], "00:00:00")


class TestParserSubcommands(unittest.TestCase):
    """Argument parsing across all subcommands."""

    def test_all_subcommands_parse_expected_values(self) -> None:
        """Each subcommand maps arguments to their documented fields."""
        parser = build_parser()
        start = parser.parse_args(["start", "write code", "--project", "Core"])
        self.assertEqual(start.command, "start")
        self.assertEqual(start.task, "write code")
        self.assertEqual(start.project, "Core")

        stop_cmd = parser.parse_args(["stop"])
        self.assertEqual(stop_cmd.command, "stop")

        switch = parser.parse_args(["switch", "review pr", "--project", "QA"])
        self.assertEqual(switch.task, "review pr")
        self.assertEqual(switch.project, "QA")

        status_cmd = parser.parse_args(["status"])
        self.assertEqual(status_cmd.command, "status")

        report = parser.parse_args(["report", "--period", "weekly"])
        self.assertEqual(report.period, "weekly")
        self.assertIsNone(report.project)

        export = parser.parse_args(["export", "--output", "log.csv"])
        self.assertEqual(export.output, "log.csv")


class TestMainCli(unittest.TestCase):
    """End-to-end CLI dispatch tests in a scratch working directory."""

    def setUp(self) -> None:
        self.scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.scratch, True)

    def run_cli(self, args_list: List[str]) -> Tuple[int, str]:
        """Run main() inside the scratch cwd capturing stdout."""
        buffer = io.StringIO()
        with contextlib.chdir(self.scratch):
            with contextlib.redirect_stdout(buffer):
                code = main(args_list)
        return code, buffer.getvalue()

    def test_start_then_status_shows_active_task(self) -> None:
        """start records a task that status then reports as active."""
        code_start, out_start = self.run_cli(
            ["start", "implement feature", "--project", "Core"]
        )
        code_status, out_status = self.run_cli(["status"])
        self.assertEqual(code_start, 0)
        self.assertIn("Started task [1] 'implement feature'", out_start)
        self.assertIn("=== ACTIVE TASK ===", out_status)
        self.assertIn("Project: Core", out_status)

    def test_status_without_active_task(self) -> None:
        """status on an empty tracker reports nothing running."""
        _, out = self.run_cli(["status"])
        self.assertIn("No task currently active.", out)

    def test_stop_reports_duration_or_idle(self) -> None:
        """stop prints the duration; repeated stops report idle state."""
        self.run_cli(["start", "brief job"])
        code, out = self.run_cli(["stop"])
        self.assertEqual(code, 0)
        self.assertIn("Stopped task 'brief job'. Duration:", out)
        _, out_idle = self.run_cli(["stop"])
        self.assertIn("No active task running.", out_idle)

    def test_switch_prints_previous_and_next_tasks(self) -> None:
        """switch summarizes the stopped and newly started tasks."""
        self.run_cli(["start", "old focus"])
        code, out = self.run_cli(["switch", "new focus", "--project", "Next"])
        self.assertEqual(code, 0)
        self.assertIn("Stopped task 'old focus'", out)
        self.assertIn("[2] 'new focus'", out)
        self.assertIn("'Next'", out)

    def test_report_renders_summary_sections(self) -> None:
        """report prints totals plus project/task breakdown blocks."""
        self.run_cli(["start", "tracked chore", "--project", "Home"])
        self.run_cli(["stop"])
        code, out = self.run_cli(["report", "--period", "daily"])
        self.assertEqual(code, 0)
        self.assertIn("=== SUMMARY REPORT (DAILY) ===", out)
        self.assertIn("--- Project Totals ---", out)
        self.assertIn("Home", out)
        self.assertIn("--- Task Breakdown ---", out)
        self.assertIn("Home: tracked chore", out)

    def test_export_command_writes_csv(self) -> None:
        """export writes the CSV file at the requested path."""
        self.run_cli(["start", "csv task"])
        target = os.path.join(self.scratch, "timesheet.csv")
        code, out = self.run_cli(["export", "--output", target])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(target))
        self.assertIn(f"Exported time logs to '{target}'", out)

    def test_no_command_prints_help(self) -> None:
        """Bare invocation shows the usage help."""
        code, out = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("usage:", out)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program starts tracking cleanly."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        buffer = io.StringIO()
        argv = [entry, "start", "cli driven task"]
        with contextlib.chdir(self.scratch):
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as ctx:
                        runpy.run_path(entry, run_name="__main__")
            storage = Path(self.scratch) / "time_tracker.json"
            self.assertTrue(storage.exists())
            payload = json.loads(storage.read_text(encoding="utf-8"))
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Started task [1]", buffer.getvalue())
        self.assertEqual(payload[0]["task"], "cli driven task")


if __name__ == "__main__":
    unittest.main()

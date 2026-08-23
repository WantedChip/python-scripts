"""
Unit tests for Interactive TODO CLI.
"""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Tuple

from main import TodoDatabase, build_parser, format_table, main


class TestTodoCLI(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test_todo.db"
        self.db = TodoDatabase(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_and_get_tasks(self):
        tid = self.db.add_task("Test task", priority="High", tags="unit,test")
        self.assertGreater(tid, 0)

        tasks = self.db.get_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Test task")
        self.assertEqual(tasks[0]["priority"], "High")

    def test_complete_and_archive(self):
        tid = self.db.add_task("Task to complete")
        self.assertTrue(self.db.complete_task(tid))

        pending = self.db.get_tasks(status_filter="pending")
        self.assertEqual(len(pending), 0)

        completed = self.db.get_tasks(status_filter="completed")
        self.assertEqual(len(completed), 1)

        archived_count = self.db.archive_task()
        self.assertEqual(archived_count, 1)

    def test_prioritize_and_tag(self):
        tid = self.db.add_task("Low priority task", priority="Low")
        self.db.update_priority(tid, "High")
        self.db.update_tags(tid, "urgent")

        tasks = self.db.get_tasks(priority_filter="High")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["tags"], "urgent")

    def test_format_table(self):
        self.db.add_task("Task 1")
        tasks = self.db.get_tasks()
        table_output = format_table(tasks)
        self.assertIn("Task 1", table_output)
        self.assertIn("ID", table_output)


class TestDatabaseEdgeCases(unittest.TestCase):
    """Fallbacks, filters, and no-op updates at the database layer."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.db = TodoDatabase(self.temp_dir / "edge.db")

    def test_invalid_add_priority_falls_back_to_medium(self) -> None:
        """An unrecognized priority string is stored as Medium."""
        tid = self.db.add_task("Odd task", priority="URGENT!!!", tags="  home  ")
        row = self.db.get_tasks(status_filter="all")[0]
        self.assertEqual(row["id"], tid)
        self.assertEqual(row["priority"], "Medium")
        self.assertEqual(row["tags"], "home")

    def test_tag_filter_uses_substring_match(self) -> None:
        """The tag filter matches tasks containing the tag substring."""
        self.db.add_task("A", tags="work urgent")
        self.db.add_task("B", tags="home")

        hits = self.db.get_tasks(tag_filter="urgent")
        self.assertEqual([t["title"] for t in hits], ["A"])

    def test_update_priority_rejects_unknown_level(self) -> None:
        """Setting an invalid priority raises ValueError."""
        tid = self.db.add_task("Prio target")
        with self.assertRaises(ValueError):
            self.db.update_priority(tid, "whenever")

    def test_operations_on_missing_ids_return_false_or_zero(self) -> None:
        """Mutations targeting absent ids report no rows affected."""
        missing_id = 9999
        self.assertFalse(self.db.complete_task(missing_id))
        self.assertFalse(self.db.update_priority(missing_id, "High"))
        self.assertFalse(self.db.update_tags(missing_id, "x"))
        self.assertFalse(self.db.delete_task(missing_id))
        self.assertEqual(self.db.archive_task(missing_id), 0)
        with self.assertRaises(ValueError):
            self.db.update_priority(missing_id, "Nope")

    def test_archive_specific_and_missing_ids(self) -> None:
        """Archiving by id flips only that task's status."""
        first = self.db.add_task("First")
        second = self.db.add_task("Second")

        self.assertEqual(self.db.archive_task(first), 1)
        archived = self.db.get_tasks(status_filter="archived")
        self.assertEqual([t["id"] for t in archived], [first])
        still_pending = self.db.get_tasks(status_filter="pending")
        self.assertIn(second, [t["id"] for t in still_pending])

    def test_delete_removes_row_permanently(self) -> None:
        """Deleting a task removes it from all future listings."""
        tid = self.db.add_task("Doomed")
        self.assertTrue(self.db.delete_task(tid))
        self.assertEqual(self.db.get_tasks(status_filter="all"), [])


class TestFormatTableRendering(unittest.TestCase):
    """ASCII table rendering for empty and populated task lists."""

    def test_empty_list_shows_placeholder(self) -> None:
        """An empty task list renders the 'no tasks' message."""
        self.assertEqual(format_table([]), "No tasks found.")

    def test_status_icons_reflect_task_state(self) -> None:
        """Completed, archived, and pending rows use distinct icons."""
        db = TodoDatabase(Path(tempfile.mkdtemp()) / "icons.db")
        db.add_task("Pending one")
        done_id = db.add_task("Finished")
        db.complete_task(done_id)
        arch_id = db.add_task("Stored away")
        db.archive_task(arch_id)

        table = format_table(db.get_tasks(status_filter="all"))
        self.assertIn("⏳ pending", table)
        self.assertIn("✔ completed", table)
        self.assertIn("📦 archived", table)


class TestCommandLine(unittest.TestCase):
    """CLI subcommands executed against a temporary database file."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.db_path = self.temp_dir / "cli.db"

    def _run(self, *args: str) -> Tuple[int, str]:
        """Run the CLI with captured stdout, returning (code, output)."""
        buf = io.StringIO()
        argv = ["--db", str(self.db_path)] + list(args)
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_build_parser_subcommand_flags(self) -> None:
        """Each subparser exposes its documented flags and defaults."""
        parser = build_parser()

        add_args = parser.parse_args(["add", "Title", "-p", "Low", "-t", "a,b"])
        self.assertEqual((add_args.title, add_args.priority), ("Title", "Low"))

        list_args = parser.parse_args(
            ["list", "--status", "all", "--tag", "work", "-p", "High"]
        )
        self.assertEqual(list_args.status, "all")
        self.assertEqual(list_args.tag, "work")
        self.assertEqual(list_args.priority, "High")

    def test_add_then_list_via_cli(self) -> None:
        """Adding a task then listing shows it in the rendered table."""
        code, out = self._run("add", "Write report", "-p", "High", "-t", "job")
        self.assertEqual(code, 0)
        self.assertIn("Task #1 added successfully.", out)

        code, out = self._run("list")
        self.assertIn("Write report", out)
        self.assertIn("⏳", out)

    def test_bare_invocation_lists_pending_tasks(self) -> None:
        """Invoking without a subcommand defaults to listing pending."""
        self._run("add", "Default view")
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("Default view", out)

    def test_done_marks_task_completed(self) -> None:
        """done flips status; unknown ids report 'not found'."""
        self._run("add", "Finish me")
        code, out = self._run("done", "1")
        self.assertIn("Task #1 completed!", out)

        code, out = self._run("done", "42")
        self.assertIn("Task #42 not found.", out)

    def test_prioritize_updates_existing_and_reports_missing(self) -> None:
        """prioritize updates levels and reports unknown ids."""
        self._run("add", "Rank me", "-p", "Low")
        code, out = self._run("prioritize", "1", "High")
        self.assertIn("priority updated to High", out)

        code, out = self._run("prioritize", "77", "Low")
        self.assertIn("Task #77 not found.", out)

    def test_tag_updates_existing_and_reports_missing(self) -> None:
        """tag rewrites labels and reports unknown ids."""
        self._run("add", "Label me")
        code, out = self._run("tag", "1", "errand weekend")
        self.assertIn("tags updated to 'errand weekend'", out)

        code, out = self._run("tag", "13", "ghost")
        self.assertIn("Task #13 not found.", out)

    def test_archive_by_id_and_bulk_completed(self) -> None:
        """archive targets a single id, or sweeps completed tasks."""
        self._run("add", "One")
        self._run("add", "Two")
        self._run("done", "2")

        code, out = self._run("archive", "1")
        self.assertIn("Archived 1 task(s).", out)

        code, out = self._run("archive")
        self.assertIn("Archived 1 task(s).", out)

    def test_delete_removes_task_and_reports_missing(self) -> None:
        """delete drops the row; repeats report not found."""
        self._run("add", "Ephemeral")
        code, out = self._run("delete", "1")
        self.assertIn("Task #1 deleted.", out)

        code, out = self._run("delete", "1")
        self.assertIn("Task #1 not found.", out)


if __name__ == "__main__":
    unittest.main()

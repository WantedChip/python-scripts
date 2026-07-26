"""
Unit tests for Interactive TODO CLI.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from main import TodoDatabase, format_table


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


if __name__ == "__main__":
    unittest.main()

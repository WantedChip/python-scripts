"""
Unit tests for Task Time Tracker CLI
"""

import os
import shutil
import tempfile
import unittest

from main import TimeSession, TimeTrackerManager, format_duration


class TestTimeTrackerHelpers(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(3665), "01:01:05")
        self.assertEqual(format_duration(0), "00:00:00")
        self.assertEqual(format_duration(59), "00:00:59")


class TestTimeSession(unittest.TestCase):
    def test_session_lifecycle(self) -> None:
        s = TimeSession(1, "Coding", "Dev")
        self.assertTrue(s.is_active())
        self.assertIsNone(s.end_time)

        s.stop()
        self.assertFalse(s.is_active())
        self.assertIsNotNone(s.end_time)
        self.assertGreaterEqual(s.duration_seconds, 0)


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


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Process Killer by Name."""

import unittest
from unittest.mock import MagicMock, patch

from main import find_target_processes, kill_processes


class TestProcessKillerByName(unittest.TestCase):

    @patch("psutil.process_iter")
    def test_find_target_processes_pattern(self, mock_iter: MagicMock) -> None:
        p1 = MagicMock()
        p1.info = {"pid": 101, "name": "python.exe", "cmdline": ["python", "main.py"]}
        p2 = MagicMock()
        p2.info = {"pid": 202, "name": "chrome.exe", "cmdline": ["chrome"]}

        mock_iter.return_value = [p1, p2]

        results = find_target_processes(pattern=r"python.*")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["pid"], 101)

    @patch("psutil.process_iter")
    def test_find_target_processes_pids(self, mock_iter: MagicMock) -> None:
        p1 = MagicMock()
        p1.info = {"pid": 101, "name": "python.exe", "cmdline": ["python"]}
        p2 = MagicMock()
        p2.info = {"pid": 202, "name": "chrome.exe", "cmdline": ["chrome"]}

        mock_iter.return_value = [p1, p2]

        results = find_target_processes(pids=[202])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "chrome.exe")

    def test_kill_processes_dry_run(self) -> None:
        mock_proc = MagicMock()
        procs = [{"pid": 101, "name": "test.exe", "proc_obj": mock_proc}]

        results = kill_processes(procs, dry_run=True)
        self.assertEqual(results[0]["status"], "SIMULATED")
        mock_proc.terminate.assert_not_called()

    def test_kill_processes_terminate(self) -> None:
        mock_proc = MagicMock()
        procs = [{"pid": 101, "name": "test.exe", "proc_obj": mock_proc}]

        results = kill_processes(procs, force=False, dry_run=False)
        self.assertEqual(results[0]["status"], "TERMINATED (SIGTERM)")
        mock_proc.terminate.assert_called_once()

    def test_kill_processes_force(self) -> None:
        mock_proc = MagicMock()
        procs = [{"pid": 101, "name": "test.exe", "proc_obj": mock_proc}]

        results = kill_processes(procs, force=True, dry_run=False)
        self.assertEqual(results[0]["status"], "KILLED (SIGKILL)")
        mock_proc.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()

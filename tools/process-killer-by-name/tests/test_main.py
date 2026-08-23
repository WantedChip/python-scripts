"""Unit tests for Process Killer by Name."""

import importlib
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Dict, List
from unittest.mock import MagicMock, PropertyMock, patch

import main as main_module
import psutil
from main import build_parser, find_target_processes, kill_processes, main


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


class TestEnumerationRobustness(unittest.TestCase):
    """Test suite for process enumeration failure handling."""

    @patch("psutil.process_iter")
    def test_disappearing_process_is_skipped(self, mock_iter: MagicMock) -> None:
        """Processes that vanish mid-scan do not abort enumeration."""
        vanishing = MagicMock()
        type(vanishing).info = PropertyMock(side_effect=psutil.NoSuchProcess(pid=999))
        healthy = MagicMock()
        healthy.info = {
            "pid": 303,
            "name": "node.exe",
            "cmdline": ["node", "server.js"],
        }
        mock_iter.return_value = [vanishing, healthy]

        results = find_target_processes(pattern=r"node")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["pid"], 303)

    def test_requires_psutil(self) -> None:
        with patch.object(main_module, "HAS_PSUTIL", False):
            with self.assertRaises(RuntimeError):
                find_target_processes(pattern="x")

    def test_import_guard_without_psutil(self) -> None:
        """Module import without psutil keeps a functional flag."""
        with patch.dict(sys.modules, {"psutil": None}):
            reloaded = importlib.reload(main_module)
            self.assertFalse(reloaded.HAS_PSUTIL)
        importlib.reload(main_module)  # restore real psutil binding

    def test_access_denied_kill_reports_failure(self) -> None:
        """A protected process yields FAILED status instead of crashing."""
        mock_proc = MagicMock()
        mock_proc.kill.side_effect = psutil.AccessDenied(pid=5)
        procs: List[Dict[str, Any]] = [
            {"pid": 5, "name": "system.exe", "proc_obj": mock_proc}
        ]
        results = kill_processes(procs, force=True, dry_run=False)
        self.assertEqual(results[0]["status"], "FAILED")
        self.assertTrue(results[0]["error"])  # error detail recorded


class TestCliEntryPoint(unittest.TestCase):
    """End-to-end tests for build_parser and main()."""

    SAMPLE_MATCH: Dict[str, Any] = {
        "pid": 4242,
        "name": "runaway.exe",
        "cmdline": ["python", "runaway.py"],
        "proc_obj": None,
    }

    def test_build_parser_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["--pattern", "node.*", "--pids", "1", "2", "-f", "-d", "-y"]
        )
        self.assertEqual(args.pattern, "node.*")
        self.assertEqual(args.pids, [1, 2])
        self.assertTrue(args.force)
        self.assertTrue(args.dry_run)
        self.assertTrue(args.yes)

    def test_main_requires_pattern_or_pids(self) -> None:
        with self.assertRaises(SystemExit):
            main([])

    def test_main_without_psutil_errors(self) -> None:
        err = io.StringIO()
        with patch.object(main_module, "HAS_PSUTIL", False), redirect_stderr(err):
            rc = main(["-p", "x"])
        self.assertEqual(rc, 1)
        self.assertIn("psutil is required", err.getvalue())

    @patch("main.find_target_processes")
    def test_main_no_matches_returns_zero(self, mock_find: MagicMock) -> None:
        mock_find.return_value = []
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["-p", "ghost"])
        self.assertEqual(rc, 0)
        self.assertIn("No matching processes found.", out.getvalue())

    @patch("main.find_target_processes")
    def test_main_dry_run_lists_without_termination(self, mock_find: MagicMock) -> None:
        proc_obj = MagicMock()
        match = dict(self.SAMPLE_MATCH, proc_obj=proc_obj)
        mock_find.return_value = [match]

        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["-p", "runaway", "--dry-run"])
        self.assertEqual(rc, 0)
        out_text = out.getvalue()
        self.assertIn("Found 1 matching process(es):", out_text)
        self.assertIn("[DRY RUN MODE]", out_text)
        proc_obj.terminate.assert_not_called()

    @patch("main.find_target_processes")
    def test_main_confirmation_declined_cancels(self, mock_find: MagicMock) -> None:
        proc_obj = MagicMock()
        match = dict(self.SAMPLE_MATCH, proc_obj=proc_obj)
        mock_find.return_value = [match]

        out = io.StringIO()
        with patch("builtins.input", return_value="n"), redirect_stdout(out):
            rc = main(["-p", "runaway"])
        self.assertEqual(rc, 0)
        self.assertIn("Operation cancelled by user.", out.getvalue())
        proc_obj.terminate.assert_not_called()

    @patch("main.find_target_processes")
    def test_main_confirmed_terminates_processes(self, mock_find: MagicMock) -> None:
        proc_obj = MagicMock()
        match = dict(self.SAMPLE_MATCH, proc_obj=proc_obj)
        mock_find.return_value = [match]

        out = io.StringIO()
        with patch("builtins.input", return_value="y"), redirect_stdout(out):
            rc = main(["-p", "runaway", "--force"])
        self.assertEqual(rc, 0)
        self.assertIn("Termination Summary:", out.getvalue())
        self.assertIn("KILLED (SIGKILL)", out.getvalue())
        proc_obj.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()

"""Unit tests for cron-doctor main.py."""

import tempfile
import unittest
from pathlib import Path

from main import CronDoctor


class TestCronDoctor(unittest.TestCase):
    """Tests for CronDoctor auditing functionality."""

    def setUp(self) -> None:
        """Set up test instance."""
        self.doctor = CronDoctor()

    def test_missing_command_detection(self) -> None:
        """Test detection of missing executable path."""
        line = "0 2 * * * /nonexistent/bin/fake_backup.sh > /dev/null 2>&1"
        issues = self.doctor.audit_entry(1, line)
        self.assertTrue(any(i.issue_type == "MISSING_EXECUTABLE" for i in issues))

    def test_silent_failure_risk(self) -> None:
        """Test detection of missing stderr redirection."""
        line = "0 * * * * python3 /tmp/script.py > /tmp/out.log"
        issues = self.doctor.audit_entry(1, line)
        self.assertTrue(any(i.issue_type == "SILENT_FAILURE_RISK" for i in issues))

    def test_overlap_warning(self) -> None:
        """Test detection of frequent schedule without process locking."""
        line = "* * * * * python3 /tmp/frequent.py > /dev/null 2>&1"
        issues = self.doctor.audit_entry(1, line)
        self.assertTrue(any(i.issue_type == "POSSIBLE_OVERLAP" for i in issues))

    def test_stale_script_path(self) -> None:
        """Test detection of non-existent script arguments."""
        line = "0 0 * * * python3 /nonexistent/script/path.py > /dev/null 2>&1"
        issues = self.doctor.audit_entry(1, line)
        self.assertTrue(any(i.issue_type == "STALE_SCRIPT_PATH" for i in issues))

    def test_file_auditing(self) -> None:
        """Test auditing an entire crontab file."""
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
            f.write("# Crontab sample\n")
            f.write("0 2 * * * /invalid/binary/path 2>&1\n")
            f_path = Path(f.name)

        try:
            issues = self.doctor.audit_file(f_path)
            self.assertGreaterEqual(len(issues), 1)
            self.assertEqual(issues[0].issue_type, "MISSING_EXECUTABLE")
        finally:
            if f_path.exists():
                f_path.unlink()


if __name__ == "__main__":
    unittest.main()

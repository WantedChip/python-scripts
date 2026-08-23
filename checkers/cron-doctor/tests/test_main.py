"""Unit tests for cron-doctor main.py."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from main import CronDoctor, main


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


class TestCronDoctorParsingEdges(unittest.TestCase):
    """Edge-case coverage for line parsing and command extraction."""

    def setUp(self) -> None:
        self.doctor = CronDoctor()

    def test_non_cron_line_yields_no_issues(self) -> None:
        """Free-form text without a schedule is ignored."""
        self.assertEqual(self.doctor.audit_entry(1, "hello world random text"), [])

    def test_extract_command_binary_empty_string(self) -> None:
        self.assertEqual(self.doctor._extract_command_binary(""), ("", []))

    def test_extract_command_binary_env_only(self) -> None:
        self.assertEqual(
            self.doctor._extract_command_binary("FOO=bar BAZ=qux"), ("", [])
        )

    def test_extract_command_binary_skips_env_prefix(self) -> None:
        binary, args = self.doctor._extract_command_binary(
            "FOO=1 python3 job.py --fast"
        )
        self.assertEqual(binary, "python3")
        self.assertEqual(args, ["job.py", "--fast"])

    def test_command_found_on_custom_path_not_flagged(self) -> None:
        python_dir = str(Path(sys.executable).parent)
        doctor = CronDoctor(custom_path=python_dir)
        exe = Path(sys.executable).name
        line = f"0 3 * * * {exe} /tmp/ok.py > /dev/null 2>&1"
        issues = doctor.audit_entry(1, line)
        self.assertFalse(any(i.issue_type == "COMMAND_NOT_FOUND" for i in issues))

    def test_permission_denied_for_non_executable_script(self) -> None:
        """An existing absolute path without +x yields PERMISSION_DENIED."""
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as tmp:
            script = Path(tmp.name)
        try:
            with mock.patch("main.os.access", return_value=False):
                issues = self.doctor.audit_entry(
                    1, f"0 3 * * * {script} > /dev/null 2>&1"
                )
            self.assertTrue(any(i.issue_type == "PERMISSION_DENIED" for i in issues))
        finally:
            script.unlink(missing_ok=True)

    def test_audit_file_missing_raises(self) -> None:
        missing = Path(tempfile.gettempdir()) / "no_such_crontab_xyz123"
        with self.assertRaises(FileNotFoundError):
            self.doctor.audit_file(missing)


class TestCronDoctorCLI(unittest.TestCase):
    """CLI entrypoint behaviour."""

    def _run_main(self, argv, expect_exit=False):
        with mock.patch.object(
            sys, "argv", ["cron-doctor"] + argv
        ), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(
            io.StringIO()
        ) as err:
            if expect_exit:
                with self.assertRaises(SystemExit) as ctx:
                    main()
                code = ctx.exception.code
            else:
                main()
                code = None
        return out.getvalue(), err.getvalue(), code

    def test_cli_healthy_entry_prints_healthy(self) -> None:
        """An existing, executable, stderr-redirected entry is healthy."""
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as tmp:
            tool = Path(tmp.name)
        os.chmod(tool, 0o755)
        try:
            out, _, _ = self._run_main(
                ["--entry", f"@daily {tool} arg1 > /dev/null 2>&1"]
            )
            self.assertIn("HEALTHY", out)
        finally:
            tool.unlink(missing_ok=True)

    def test_cli_entry_with_issues_prints_report(self) -> None:
        out, _, _ = self._run_main(
            ["--entry", "0 0 * * * /nonexistent/tool > /dev/null 2>&1"]
        )
        self.assertIn("[ERROR] Line 1: MISSING_EXECUTABLE", out)
        self.assertIn("Details:", out)

    def test_cli_file_mode(self) -> None:
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp:
            tmp.write("0 0 * * * /nope/missing > /dev/null 2>&1\n")
            path = Path(tmp.name)
        try:
            out, _, _ = self._run_main(["--file", str(path)])
            self.assertIn("MISSING_EXECUTABLE", out)
        finally:
            path.unlink(missing_ok=True)

    def test_cli_no_args_exits_two(self) -> None:
        _, err, code = self._run_main([], expect_exit=True)
        self.assertEqual(code, 2)
        self.assertIn("--file", err)


class TestCronDoctorModuleMain(unittest.TestCase):
    """The script's __main__ guard runs the CLI."""

    def test_help_via_subprocess(self) -> None:
        script = Path(__file__).resolve().parent.parent / "main.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Audit crontabs", result.stdout)


if __name__ == "__main__":
    unittest.main()

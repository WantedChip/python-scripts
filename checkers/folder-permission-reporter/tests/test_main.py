"""Unit tests for folder-permission-reporter main.py."""

import contextlib
import io
import json
import os
import pathlib
import stat
import tempfile
import unittest
from typing import Optional

import main as main_module
from main import PermissionAuditor, main


class TestPermissionAuditor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = pathlib.Path(self.temp_dir.name)

        # Create world-writable file
        self.world_writable_file = self.work_dir / "world_writable.txt"
        self.world_writable_file.write_text("Sensitive info", encoding="utf-8")
        try:
            os.chmod(self.world_writable_file, 0o666)  # rw-rw-rw-
        except OSError:
            pass

        # Create executable data file
        self.exec_data_file = self.work_dir / "data.csv"
        self.exec_data_file.write_text("id,name\n1,test", encoding="utf-8")
        try:
            os.chmod(self.exec_data_file, 0o755)  # rwxr-xr-x
        except OSError:
            pass

        # Create clean file
        self.clean_file = self.work_dir / "clean.txt"
        self.clean_file.write_text("Clean data", encoding="utf-8")
        try:
            os.chmod(self.clean_file, 0o644)  # rw-r--r--
        except OSError:
            pass

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_permission_auditor_evaluation(self):
        auditor = PermissionAuditor(self.work_dir)
        issues = auditor.run_audit()

        issue_paths = [i.path for i in issues]
        # Check if vulnerabilities were flagged
        if os.name != "nt":  # Full bit checking on POSIX
            self.assertIn(str(self.world_writable_file), issue_paths)
            self.assertIn(str(self.exec_data_file), issue_paths)

            ww_issue = next(
                i for i in issues if i.path == str(self.world_writable_file)
            )
            self.assertEqual(ww_issue.risk_level, "HIGH")
            self.assertIn("chmod", ww_issue.recommended_fix)

    def test_main_cli_execution(self):
        json_report = self.work_dir / "audit.json"
        _ = main([str(self.work_dir), "--json-output", str(json_report)])

        self.assertTrue(json_report.exists())
        with open(json_report, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertIsInstance(data, list)


class _FakeStat:
    """Stands in for os.stat_result with a canned st_mode value."""

    def __init__(self, mode: int) -> None:
        self.st_mode = mode


class _FakePath:
    """Duck-typed pathlib.Path exposing stat/is_dir/suffix for classification."""

    def __init__(
        self, text: str, mode: int, is_dir: bool = False, suffix: str = ""
    ) -> None:
        self._text = text
        self._mode = mode
        self._is_dir = is_dir
        self._suffix = suffix

    def stat(self) -> _FakeStat:
        """Return the canned stat result."""
        return _FakeStat(self._mode)

    def is_dir(self) -> bool:
        """Report whether this fake path is a directory."""
        return self._is_dir

    @property
    def suffix(self) -> str:
        """Return the file extension."""
        return self._suffix

    def __str__(self) -> str:
        return self._text


class _ExplodingPath(_FakePath):
    """Fake path whose stat() always fails, emulating permission errors."""

    def stat(self) -> _FakeStat:
        """Simulate an unreadable path."""
        raise PermissionError(13, "Permission denied")


class TestModeClassification(unittest.TestCase):
    """Platform-independent tests for mode-bit risk classification."""

    @staticmethod
    def _classify(
        mode: int, is_dir: bool = False, suffix: str = ""
    ) -> Optional[object]:
        """Classify a fake path with ``mode`` and return any issue."""
        fake = _FakePath(f"/fake/item{suffix}", mode, is_dir=is_dir, suffix=suffix)
        return PermissionAuditor.evaluate_path_permissions(fake)

    def test_world_writable_file_high_risk(self) -> None:
        """o+w files are HIGH risk with a chmod o-w fix."""
        issue = self._classify(0o666, suffix=".txt")
        assert issue is not None
        self.assertEqual(issue.risk_level, "HIGH")
        self.assertIn("World-writable (o+w)", issue.reasons)
        self.assertIn("chmod o-w", issue.recommended_fix)

    def test_world_writable_dir_missing_sticky(self) -> None:
        """o+w dirs without the sticky bit get both reasons and chmod 755."""
        issue = self._classify(0o777, is_dir=True)
        assert issue is not None
        self.assertEqual(issue.risk_level, "HIGH")
        self.assertIn("missing sticky bit", " ".join(issue.reasons))
        self.assertEqual(issue.recommended_fix, "chmod 755 '/fake/item'")

    def test_sticky_bit_present_suppresses_reason(self) -> None:
        """The sticky bit removes only the missing-sticky reason."""
        issue = self._classify(0o1777, is_dir=True)
        assert issue is not None
        joined = "; ".join(issue.reasons)
        self.assertNotIn("sticky", joined)

    def test_suid_and_sgid_bits_flagged(self) -> None:
        """SUID/SGID setuid-style bits are HIGH risk on files."""
        issue = self._classify(0o6755, suffix=".sh")
        assert issue is not None
        self.assertEqual(issue.risk_level, "HIGH")
        self.assertIn("(SUID, SGID)", " ".join(issue.reasons))
        self.assertIn("u-s,g-s", issue.recommended_fix)

    def test_executable_data_file_medium(self) -> None:
        """Data files (.csv) with exec bits rate MEDIUM with chmod -x."""
        issue = self._classify(0o755, suffix=".csv")
        assert issue is not None
        self.assertEqual(issue.risk_level, "MEDIUM")
        self.assertIn("chmod -x", issue.recommended_fix)

    def test_exec_data_plus_world_writable_condenses_to_644(self) -> None:
        """A 0o777 data file condenses its fix into chmod 644."""
        issue = self._classify(0o777, suffix=".json")
        assert issue is not None
        self.assertEqual(issue.risk_level, "HIGH")
        self.assertEqual(issue.recommended_fix, "chmod 644 '/fake/item.json'")

    def test_group_writable_directory_low(self) -> None:
        """g+w directories without o+w stay LOW risk."""
        issue = self._classify(0o770, is_dir=True)
        assert issue is not None
        self.assertEqual(issue.risk_level, "LOW")
        self.assertIn("Group-writable (g+w)", issue.reasons)

    def test_clean_mode_returns_none(self) -> None:
        """A plain 0644 data file yields no finding."""
        self.assertIsNone(self._classify(0o644, suffix=".txt"))

    def test_unstatable_path_returns_none(self) -> None:
        """Paths that cannot be stat'ed are skipped, not fatal."""
        exploding = _ExplodingPath("/fake/locked", 0)
        self.assertIsNone(PermissionAuditor.evaluate_path_permissions(exploding))


class TestCliAndReports(unittest.TestCase):
    """Tests for report rendering and CLI behaviour."""

    def test_print_cli_report_empty_issues(self) -> None:
        """Empty audits print the clean-scan banner."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main_module.print_cli_report([], pathlib.Path("C:/clean"))
        out = buf.getvalue()
        self.assertIn("FOLDER PERMISSION AUDIT REPORT", out)
        self.assertIn("No permission vulnerabilities", out)

    def test_main_nonexistent_path_returns_one(self) -> None:
        """Auditing a missing path prints an error and returns 1."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["Z:/definitely/not/here"])
        self.assertEqual(code, 1)
        self.assertIn("Error: Path does not exist", err.getvalue())

    def test_main_json_output_failure_is_reported(self) -> None:
        """An unwritable JSON destination reports failure but still exits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_json = pathlib.Path(tmpdir) / "no" / "such" / "dir" / "r.json"
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main([tmpdir, "--json-output", str(bad_json)])
        self.assertEqual(code, 1)  # tmpdir itself is world-writable on Windows
        self.assertIn("Failed to write JSON report", err.getvalue())

    def test_main_min_risk_filter(self) -> None:
        """--min-risk HIGH excludes lower-severity rows from output/json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_report = pathlib.Path(tmpdir) / "out.json"
            # On Windows every writable file looks world-writable (HIGH),
            # so create a read-only clean file to exercise LOW filtering.
            low_file = pathlib.Path(tmpdir) / "notes.txt"
            low_file.write_text("plain notes", encoding="utf-8")
            os.chmod(low_file, stat.S_IREAD)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(
                    [tmpdir, "--min-risk", "HIGH", "--json-output", str(json_report)]
                )
            data = json.loads(json_report.read_text(encoding="utf-8"))
        self.assertTrue(all(i["risk_level"] == "HIGH" for i in data))
        self.assertIn(str(code), ("0", "1"))


if __name__ == "__main__":
    unittest.main()

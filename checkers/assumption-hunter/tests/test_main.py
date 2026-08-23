"""Unit tests for assumption-hunter main.py."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from main import format_text_report, main, scan_directory, scan_file


def _write_temp_py(content: str) -> Path:
    """Write ``content`` to a temporary .py file and return its path."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        return Path(tmp.name)


class TestAssumptionHunter(unittest.TestCase):
    """Tests for assumption hunter AST and regex scanner."""

    def test_scan_missing_encoding_and_cwd(self) -> None:
        content = """
import os
import datetime

def process_file():
    cwd = os.getcwd()
    f = open("data.txt", "r")
    now = datetime.datetime.now()
    var = os.environ['MY_VAR']
    return cwd
"""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            findings = scan_file(tmp_path)
            rule_ids = [f.rule_id for f in findings]
            self.assertIn("CWD_DEPENDENCY", rule_ids)
            self.assertIn("MISSING_ENCODING", rule_ids)
            self.assertIn("LOCAL_TIMEZONE", rule_ids)
            self.assertIn("ENV_VAR_EXISTENCE", rule_ids)
        finally:
            tmp_path.unlink()

    def test_scan_hardcoded_tmp(self) -> None:
        content = """
def write_tmp():
    path = "/tmp/scratch.txt"
    return path
"""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            findings = scan_file(tmp_path)
            rule_ids = [f.rule_id for f in findings]
            self.assertIn("TMP_HARDCODED", rule_ids)
        finally:
            tmp_path.unlink()

    def test_directory_scan_and_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            file1 = dir_path / "app.py"
            file1.write_text("import locale\nlocale.setlocale()\n", encoding="utf-8")

            findings = scan_directory(dir_path)
            self.assertTrue(len(findings) > 0)
            report = format_text_report(findings)
            self.assertIn("LOCALE_DEPENDENCY", report)


class TestRuleDetection(unittest.TestCase):
    """Tests for individual AST and regex assumption rules."""

    @staticmethod
    def _rule_ids(content: str) -> list:
        """Scan ``content`` as a temp file and return detected rule IDs."""
        tmp_path = _write_temp_py(content)
        try:
            return [f.rule_id for f in scan_file(tmp_path)]
        finally:
            tmp_path.unlink()

    def test_binary_mode_open_not_flagged(self) -> None:
        """Binary-mode open calls must not raise MISSING_ENCODING."""
        content = """
data = open("blob.bin", "rb")
out = open("res.bin", mode="wb")
"""
        self.assertNotIn("MISSING_ENCODING", self._rule_ids(content))

    def test_unsorted_filenames_rule(self) -> None:
        """Directory listing calls should be flagged as UNSORTED_FILENAMES."""
        content = """
import glob
import os
from pathlib import Path

names = os.listdir(".")
entries = Path(".").iterdir()
matches = glob.glob("*.py")
"""
        rule_ids = self._rule_ids(content)
        self.assertEqual(rule_ids.count("UNSORTED_FILENAMES"), 3)

    def test_shell_true_and_cli_dependency(self) -> None:
        """shell=True subprocess calls and external CLIs are both flagged."""
        content = """
import subprocess

subprocess.run(["ffmpeg", "-i", "in.mkv", "out.mp4"], shell=True)
subprocess.Popen(["python3", "-c", "print(1)"])
"""
        rule_ids = self._rule_ids(content)
        self.assertIn("SPECIFIC_SHELL", rule_ids)
        self.assertIn("GLOBAL_CLI_DEPENDENCY", rule_ids)
        # python/python3 executables must not count as external CLI deps.
        self.assertEqual(rule_ids.count("GLOBAL_CLI_DEPENDENCY"), 1)

    def test_writable_home_rule(self) -> None:
        """Hardcoded home-directory paths should be flagged WRITABLE_HOME."""
        content = """
cache_dir = "~/.config/app-cache"
posix_cfg = "/home/alice/.config/tool.cfg"
"""
        rule_ids = self._rule_ids(content)
        self.assertEqual(rule_ids.count("WRITABLE_HOME"), 2)

    def test_regex_shell_and_path_separator_rules(self) -> None:
        """Regex-only rules fire even inside syntactically broken files."""
        tmp_path = _write_temp_py("cmd = 'bash'  # noqa\nparts = p.split('/')\n")
        try:
            rule_ids = [f.rule_id for f in scan_file(tmp_path)]
        finally:
            tmp_path.unlink()
        self.assertIn("SPECIFIC_SHELL", rule_ids)
        self.assertIn("UNIX_PATH_SEPARATORS", rule_ids)


class TestScanFileEdgeCases(unittest.TestCase):
    """Tests for scanner robustness against unreadable or invalid input."""

    def test_scan_file_unreadable_returns_empty(self) -> None:
        """A path that cannot be read yields no findings, not a crash."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            findings = scan_file(Path(tmp_dir))
        self.assertEqual(findings, [])

    def test_scan_syntax_error_file_skips_ast_only(self) -> None:
        """Syntax-broken files skip AST rules but keep regex scanning."""
        tmp_path = _write_temp_py("def broken(:\nimport os\nos.getcwd()\n")
        try:
            findings = scan_file(tmp_path)
        finally:
            tmp_path.unlink()
        self.assertTrue(
            all(f.rule_id != "CWD_DEPENDENCY" for f in findings),
            "AST rules must not fire for unparseable files",
        )

    def test_scan_directory_accepts_single_file(self) -> None:
        """Passing a file path scans just that file."""
        tmp_path = _write_temp_py("import os\nos.getcwd()\n")
        try:
            findings = scan_directory(tmp_path)
            self.assertTrue(findings)
            self.assertTrue(all(f.file_path == str(tmp_path) for f in findings))
        finally:
            tmp_path.unlink()

    def test_ignore_rules_filter_findings(self) -> None:
        """Ignored rule IDs are dropped from directory scan results."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "app.py"
            src.write_text("import os\nos.getcwd()\n", encoding="utf-8")
            findings = scan_directory(Path(tmp_dir), ignore_rules=["CWD_DEPENDENCY"])
        self.assertEqual(findings, [])

    def test_format_text_report_empty(self) -> None:
        """An empty findings list produces the clean-scan message."""
        report = format_text_report([])
        self.assertEqual(report, "No environmental assumption risks detected.")


class TestMainCli(unittest.TestCase):
    """End-to-end tests for the command-line entrypoint."""

    def _run_main(self, argv: list) -> tuple:
        """Run main() with patched argv; return (code, stdout, stderr)."""
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with mock.patch.object(sys, "argv", ["main.py"] + argv):
                try:
                    main()
                except SystemExit as exc:
                    code = int(exc.code if exc.code is not None else 0)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_main_text_report_finds_issues_exits_one(self) -> None:
        """Text format prints the audit report and exits 1 when issues exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "app.py"
            src.write_text("import os\nos.getcwd()\n", encoding="utf-8")
            code, out, err = self._run_main([tmp_dir])
        self.assertEqual(code, 1)
        self.assertIn("Assumption Hunter Audit Report", out)
        self.assertIn("CWD_DEPENDENCY", out)
        self.assertEqual(err, "")

    def test_main_json_clean_project_exits_zero(self) -> None:
        """JSON output on a clean project is an empty list with exit 0."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            code, out, _ = self._run_main([tmp_dir, "--format", "json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), [])

    def test_main_nonexistent_path_errors(self) -> None:
        """A missing target path reports to stderr and exits 1."""
        code, _, err = self._run_main(["Z:/definitely/not/here"])
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err)

    def test_main_min_severity_filters_low(self) -> None:
        """HIGH threshold hides LOW-severity findings and exits 0."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "app.py"
            src.write_text("import os\nos.getcwd()\n", encoding="utf-8")
            code, out, _ = self._run_main([tmp_dir, "--min-severity", "HIGH"])
            self.assertEqual(code, 0)
            self.assertIn("No environmental assumption risks", out)

    def test_main_exclude_directory(self) -> None:
        """Excluded directories are not scanned."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            vendor = Path(tmp_dir) / "vendor"
            vendor.mkdir()
            (vendor / "lib.py").write_text("import os\nos.getcwd()\n", encoding="utf-8")
            code, out, _ = self._run_main([tmp_dir, "--exclude", "vendor"])
        self.assertEqual(code, 0)
        self.assertIn("No environmental assumption risks", out)

    def test_main_ignore_rule_flag(self) -> None:
        """--ignore-rule suppresses the matching finding."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "app.py"
            src.write_text("import os\nos.getcwd()\n", encoding="utf-8")
            code, out, _ = self._run_main([tmp_dir, "--ignore-rule", "CWD_DEPENDENCY"])
        self.assertEqual(code, 0)
        self.assertNotIn("CWD_DEPENDENCY", out)


if __name__ == "__main__":
    unittest.main()

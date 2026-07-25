"""Unit tests for assumption-hunter main.py."""

import tempfile
import unittest
from pathlib import Path

from main import format_text_report, scan_directory, scan_file


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


if __name__ == "__main__":
    unittest.main()

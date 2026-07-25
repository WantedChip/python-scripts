import json
import os
import pathlib
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()

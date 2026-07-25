"""Unit tests for file-share-audit main.py."""

import os
import tempfile
import unittest

from main import FileShareAuditor


class TestFileShareAuditor(unittest.TestCase):

    def test_detect_sensitive_env_file_and_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock .env file with an API key
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("OPENAI_KEY=sk-abc123xyz45678901234567890123456\n")

            auditor = FileShareAuditor(username="testuser")
            report = auditor.audit_directory(tmpdir)

            self.assertGreaterEqual(report.high_count, 1)
            categories = [finding.category for finding in report.findings]
            self.assertIn("Sensitive File", categories)

    def test_detect_username_in_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            user_subdir = os.path.join(tmpdir, "testuser_data")
            os.makedirs(user_subdir, exist_ok=True)
            dummy_file = os.path.join(user_subdir, "sample.txt")
            with open(dummy_file, "w", encoding="utf-8") as f:
                f.write("Clean content")

            auditor = FileShareAuditor(username="testuser")
            report = auditor.audit_directory(tmpdir)

            categories = [finding.category for finding in report.findings]
            self.assertIn("Username Exposure", categories)

    def test_clean_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            clean_file = os.path.join(tmpdir, "readme.txt")
            with open(clean_file, "w", encoding="utf-8") as f:
                f.write("Hello world, this is clean public documentation.")

            auditor = FileShareAuditor(username="nonexistentuser")
            report = auditor.audit_directory(tmpdir)

            self.assertEqual(len(report.findings), 0)


if __name__ == "__main__":
    unittest.main()

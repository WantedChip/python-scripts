import shutil
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path

from main import SecretHistoryChecker


class TestSecretHistoryChecker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.repo_dir = Path(self.temp_dir)
        # Initialize test git repo
        subprocess.run(  # nosec B603 B607
            ["git", "init"],
            cwd=str(self.repo_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(  # nosec B603 B607
            ["git", "config", "user.name", "Test User"],
            cwd=str(self.repo_dir),
            check=True,
        )
        subprocess.run(  # nosec B603 B607
            ["git", "config", "user.email", "test@example.com"],
            cwd=str(self.repo_dir),
            check=True,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_find_deleted_secret_in_commit_history(self):
        secret_file = self.repo_dir / "config.txt"

        # Step 1: Commit file with secret
        secret_file.write_text(
            "API_SECRET_KEY=super_secret_token_123\n", encoding="utf-8"
        )
        subprocess.run(  # nosec B603 B607
            ["git", "add", "config.txt"], cwd=str(self.repo_dir), check=True
        )
        subprocess.run(  # nosec B603 B607
            ["git", "commit", "-m", "Add secret config"],
            cwd=str(self.repo_dir),
            check=True,
        )

        # Step 2: Delete secret in new commit
        secret_file.write_text("API_SECRET_KEY=REDACTED\n", encoding="utf-8")
        subprocess.run(  # nosec B603 B607
            ["git", "add", "config.txt"], cwd=str(self.repo_dir), check=True
        )
        subprocess.run(  # nosec B603 B607
            ["git", "commit", "-m", "Remove secret config"],
            cwd=str(self.repo_dir),
            check=True,
        )

        # Step 3: Run checker
        checker = SecretHistoryChecker(self.repo_dir)
        findings = checker.audit_all("super_secret_token_123")

        self.assertGreaterEqual(len(findings), 1)
        self.assertEqual(findings[0].file_path, "config.txt")
        self.assertEqual(findings[0].author, "Test User")

    def test_clean_history_returns_no_findings(self):
        clean_file = self.repo_dir / "app.py"
        clean_file.write_text("print('Hello World')\n", encoding="utf-8")
        subprocess.run(  # nosec B603 B607
            ["git", "add", "app.py"], cwd=str(self.repo_dir), check=True
        )
        subprocess.run(  # nosec B603 B607
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(self.repo_dir),
            check=True,
        )

        checker = SecretHistoryChecker(self.repo_dir)
        findings = checker.audit_all("non_existent_secret_key_999")
        self.assertEqual(len(findings), 0)


if __name__ == "__main__":
    unittest.main()

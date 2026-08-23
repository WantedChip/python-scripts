import json
import os
import shutil
import stat
import subprocess  # nosec B404
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

from main import Finding, SecretHistoryChecker, main, parse_args


def _rmtree_onexc(func, path, exc):
    """Clear the read-only flag git sets on loose objects, then retry removal."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


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
        shutil.rmtree(self.temp_dir, onexc=_rmtree_onexc)

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


class _FakeGit:
    """Dispatches fake git command output without touching a real repository."""

    def __init__(self, responses: Dict[str, str]):
        self.responses = responses
        self.calls: List[List[str]] = []

    def run_git(self, cmd: List[str]) -> str:
        self.calls.append(cmd)
        joined = " ".join(cmd)
        for key, output in self.responses.items():
            if joined.startswith(key):
                return output
        return ""


class TestSecretCheckerWithMockedGit(unittest.TestCase):
    """Tests for search logic using fully mocked git subprocess boundaries."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_init_rejects_directory_without_git(self) -> None:
        with patch.object(SecretHistoryChecker, "_run_git", return_value=""):
            with self.assertRaises(ValueError):
                SecretHistoryChecker(self.repo_dir)

    def test_init_accepts_git_work_tree_confirmation(self) -> None:
        with patch.object(SecretHistoryChecker, "_run_git", return_value="true\n"):
            checker = SecretHistoryChecker(self.repo_dir)
            self.assertTrue(checker._is_git_repo())

    def test_run_git_returns_stdout_when_git_fails(self) -> None:
        """git grep/log exit non-zero on no-match; stdout must still surface."""
        checker = SecretHistoryChecker(self._mark_as_repo())
        failing = subprocess.CalledProcessError(1, "git", output="partial output")
        with patch("main.subprocess.run", side_effect=failing):
            out = checker._run_git(["git", "log", "-S", "x"])
        self.assertEqual(out, "partial output")

    def _mark_as_repo(self) -> Path:
        (self.repo_dir / ".git").mkdir()
        return self.repo_dir

    def test_search_stashes_finds_secret_in_stash_diff(self) -> None:
        fake = _FakeGit(
            {
                "git stash list": (
                    "stash@{0}: WIP on main: abc123 add config\n"
                    "malformed line without ref\n"
                ),
                "git stash show -p stash@{0}": ("+API_KEY=tok_live_abc123\n-context\n"),
                "git stash show -p stash@{1}": "",
            }
        )
        checker = SecretHistoryChecker(self._mark_as_repo())
        with patch.object(checker, "_run_git", side_effect=fake.run_git):
            findings = checker.search_stashes("tok_live_abc123")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].location_type, "stash")
        self.assertEqual(findings[0].identifier, "stash@{0}")
        self.assertIn("WIP on main", findings[0].ref)

    def test_search_stashes_regex_mode(self) -> None:
        fake = _FakeGit(
            {
                "git stash list": "stash@{0}: WIP on main: abc add cfg\n",
                "git stash show -p stash@{0}": "+TOKEN=tok_live_99887766\n",
            }
        )
        checker = SecretHistoryChecker(self._mark_as_repo())
        with patch.object(checker, "_run_git", side_effect=fake.run_git):
            findings = checker.search_stashes(r"tok_live_\d+", is_regex=True)
        self.assertEqual(len(findings), 1)

    def test_search_stashes_without_stashes_is_empty(self) -> None:
        fake = _FakeGit({"git stash list": ""})
        checker = SecretHistoryChecker(self._mark_as_repo())
        with patch.object(checker, "_run_git", side_effect=fake.run_git):
            self.assertEqual(checker.search_stashes("any"), [])

    def test_search_reflog_deduplicates_and_matches_secret(self) -> None:
        fake = _FakeGit(
            {
                "git reflog": (
                    "HEAD@{0}|abc123def|commit: rotate keys\n"
                    "HEAD@{1}|abc123def|commit: amend rotate keys\n"
                    "HEAD@{2}|999888|commit: docs only\n"
                ),
                "git show abc123def": "diff --git a/k.env +KEY=reflog_secret_1\n",
                "git show 999888": "just docs",
            }
        )
        checker = SecretHistoryChecker(self._mark_as_repo())
        with patch.object(checker, "_run_git", side_effect=fake.run_git):
            findings = checker.search_reflog("reflog_secret_1")

        # Same commit reached via two reflog entries yields one finding.
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].identifier, "abc123def")
        self.assertEqual(findings[0].snippet, "commit: rotate keys")

    def test_search_reflog_regex_mode_no_match(self) -> None:
        fake = _FakeGit(
            {
                "git reflog": "HEAD@{0}|aaa111|commit: init\n",
                "git show aaa111": "nothing here",
            }
        )
        checker = SecretHistoryChecker(self._mark_as_repo())
        with patch.object(checker, "_run_git", side_effect=fake.run_git):
            findings = checker.search_reflog(r"secret_\d+", is_regex=True)
        self.assertEqual(findings, [])

    def test_search_reflog_without_reflog_entries_is_empty(self) -> None:
        fake = _FakeGit({"git reflog": ""})
        checker = SecretHistoryChecker(self._mark_as_repo())
        with patch.object(checker, "_run_git", side_effect=fake.run_git):
            self.assertEqual(checker.search_reflog("any"), [])


class TestSecretAuditCli(unittest.TestCase):
    """CLI tests with the git boundary mocked at the checker level."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)
        (self.repo_dir / ".git").mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _finding(identifier: str = "abc123") -> Finding:
        return Finding(
            location_type="commit",
            identifier=identifier,
            date="2026-08-01 12:00:00 +0000",
            author="Test User",
            ref="(HEAD -> main)",
            file_path="config.env",
            snippet="Match found via pickaxe (-S)",
        )

    def test_parse_args_defaults_and_flags(self) -> None:
        parsed = parse_args(["-s", "tok"])
        self.assertEqual(parsed.secret, "tok")
        self.assertEqual(parsed.repo, Path("."))
        self.assertFalse(parsed.regex)
        self.assertFalse(parsed.json)

        parsed = parse_args(
            ["--secret", "tok", "--repo", "/tmp/r", "--regex", "--json"]
        )
        self.assertEqual(parsed.repo, Path("/tmp/r"))
        self.assertTrue(parsed.regex)
        self.assertTrue(parsed.json)

    def test_main_clean_history_prints_success(self) -> None:
        with patch.object(SecretHistoryChecker, "audit_all", return_value=[]):
            buf = StringIO()
            with redirect_stdout(buf):
                ret = main(["-s", "gone_secret", "-r", str(self.repo_dir)])
        self.assertEqual(ret, 0)
        self.assertIn("SUCCESS", buf.getvalue())

    def test_main_lists_findings_for_leaked_secret(self) -> None:
        with patch.object(
            SecretHistoryChecker,
            "audit_all",
            return_value=[self._finding()],
        ):
            buf = StringIO()
            with redirect_stdout(buf):
                ret = main(["-s", "leaked_secret", "-r", str(self.repo_dir)])
        self.assertEqual(ret, 0)
        output = buf.getvalue()
        self.assertIn("WARNING", output)
        self.assertIn("[1] Location: COMMIT", output)
        self.assertIn("config.env", output)

    def test_main_json_output_serializes_findings(self) -> None:
        with patch.object(
            SecretHistoryChecker,
            "audit_all",
            return_value=[self._finding()],
        ):
            buf = StringIO()
            with redirect_stdout(buf):
                ret = main(["-s", "leak", "--json", "-r", str(self.repo_dir)])
        self.assertEqual(ret, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload[0]["location_type"], "commit")
        self.assertEqual(payload[0]["file_path"], "config.env")

    def test_main_returns_error_on_checker_failure(self) -> None:
        err = StringIO()
        with patch.object(
            SecretHistoryChecker,
            "audit_all",
            side_effect=RuntimeError("git exploded"),
        ):
            with redirect_stderr(err):
                ret = main(["-s", "x", "-r", str(self.repo_dir)])
        self.assertEqual(ret, 1)
        self.assertIn("Error:", err.getvalue())


if __name__ == "__main__":
    unittest.main()

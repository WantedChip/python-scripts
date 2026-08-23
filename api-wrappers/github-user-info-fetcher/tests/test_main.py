"""Unit tests for GitHub User Info Fetcher."""

import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    analyze_languages,
    calculate_total_stars,
    export_json,
    fetch_json,
    fetch_user_profile,
    fetch_user_repos,
    format_user_summary,
    main,
)


class TestGitHubUserFetcher(unittest.TestCase):
    """Test suite for GitHub user info fetcher functions."""

    def setUp(self) -> None:
        self.sample_profile = {
            "login": "octocat",
            "name": "The Octocat",
            "bio": "Building tools for developers.",
            "company": "@github",
            "location": "San Francisco",
            "followers": 1000,
            "following": 5,
            "public_repos": 8,
            "public_gists": 2,
            "created_at": "2011-01-25T18:44:36Z",
            "html_url": "https://github.com/octocat",
        }

        self.sample_repos = [
            {
                "name": "repo1",
                "language": "Python",
                "stargazers_count": 10,
                "forks_count": 2,
                "html_url": "http://...",
            },
            {
                "name": "repo2",
                "language": "Python",
                "stargazers_count": 5,
                "forks_count": 1,
                "html_url": "http://...",
            },
            {
                "name": "repo3",
                "language": "Go",
                "stargazers_count": 20,
                "forks_count": 4,
                "html_url": "http://...",
            },
        ]

    def test_analyze_languages(self) -> None:
        """Test language frequency calculation across repos."""
        langs = analyze_languages(self.sample_repos)
        self.assertEqual(langs[0], ("Python", 2))
        self.assertEqual(langs[1], ("Go", 1))

    def test_format_user_summary(self) -> None:
        """Test formatting profile summary output."""
        summary = format_user_summary(self.sample_profile, self.sample_repos)
        self.assertIn("@octocat", summary)
        self.assertIn("The Octocat", summary)
        self.assertIn("Python (2)", summary)
        self.assertIn("Total Stars   : 35", summary)
        self.assertIn("Total Forks   : 7", summary)

    @patch("main.fetch_json")
    def test_fetch_user_profile(self, mock_fetch: MagicMock) -> None:
        """Test fetching GitHub user profile."""
        mock_fetch.return_value = self.sample_profile
        profile = fetch_user_profile("octocat")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["login"], "octocat")
        mock_fetch.assert_called_once_with("https://api.github.com/users/octocat")

    @patch("main.fetch_json")
    def test_fetch_user_repos(self, mock_fetch: MagicMock) -> None:
        """Test fetching user repos with pagination."""
        mock_fetch.side_effect = [self.sample_repos]
        repos = fetch_user_repos("octocat")
        self.assertEqual(len(repos), 3)

    def test_export_json(self) -> None:
        """Test exporting profile data to JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "user_stats.json")
            success = export_json(self.sample_profile, self.sample_repos, file_path)
            self.assertTrue(success)
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            self.assertEqual(content["user"]["login"], "octocat")
            self.assertEqual(content["metrics"]["total_stars"], 35)

    def test_export_json_oserror(self) -> None:
        """Unwritable export targets report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing" / "user.json")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = export_json(self.sample_profile, self.sample_repos, bad_path)
        self.assertFalse(success)
        self.assertIn("Error saving JSON export", stderr.getvalue())

    def test_calculate_total_stars(self) -> None:
        """Star counts sum across repos with missing keys counting zero."""
        repos = [
            {"stargazers_count": 10},
            {"stargazers_count": 5},
            {"name": "no-stars-repo"},
        ]
        self.assertEqual(calculate_total_stars(repos), 15)


class TestNetworkLayer(unittest.TestCase):
    """Tests for the low-level GitHub API HTTP helper."""

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_success(self, mock_urlopen: MagicMock) -> None:
        """A 200 response with valid JSON is parsed into a dictionary."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"login": "octocat"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_json("https://api.github.com/users/octocat")
        self.assertEqual(result, {"login": "octocat"})
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(
            request.headers.get("Accept"), "application/vnd.github.v3+json"
        )

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_non_200_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Non-200 status codes yield None without raising."""
        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.read.return_value = b"rate limited"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("https://api.github.com/users/x"))

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_error_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Network errors are reported to stderr and mapped to None."""
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_json("https://api.github.com/users/x")
        self.assertIsNone(result)
        self.assertIn(
            "Error fetching https://api.github.com/users/x", stderr.getvalue()
        )

    @patch("main.fetch_json")
    def test_fetch_user_repos_non_list_payload(self, mock_fetch: MagicMock) -> None:
        """Non-list payloads (e.g. error dicts) map to an empty repo list."""
        mock_fetch.return_value = {"message": "Not Found"}
        self.assertEqual(fetch_user_repos("ghost-user"), [])

    @patch("main.fetch_json")
    def test_fetch_user_profile_url_encoding(self, mock_fetch: MagicMock) -> None:
        """Usernames are URL-quoted in the profile endpoint path."""
        mock_fetch.return_value = {}
        fetch_user_profile("octo cat")
        self.assertIn("/users/octo%20cat", mock_fetch.call_args[0][0])


class TestSummaryEdgeCases(unittest.TestCase):
    """Tests for summary rendering fallbacks."""

    def test_summary_defaults_for_sparse_profile(self) -> None:
        """Missing profile fields render their documented placeholders."""
        summary = format_user_summary({"login": "ghost"}, [])
        self.assertIn("@ghost", summary)
        self.assertIn("No bio provided.", summary)
        self.assertIn("Company    : N/A", summary)
        self.assertIn("Location   : N/A", summary)
        self.assertIn("Top Languages : None detected", summary)

    def test_summary_truncates_long_bio(self) -> None:
        """Bios longer than 60 characters are truncated with ellipsis."""
        long_bio = "x" * 80
        summary = format_user_summary({"login": "g", "bio": long_bio}, [])
        self.assertIn("...", summary)
        self.assertNotIn("x" * 70, summary)

    def test_analyze_languages_ignores_null_language(self) -> None:
        """Repos without a primary language do not affect the ranking."""
        langs = analyze_languages([{"language": None}, {"name": "r2"}])
        self.assertEqual(langs, [])


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    def _run_cli(self, *args: str) -> Any:
        """Run main() with patched argv; capture streams and exit code."""
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code: Any = None
        argv = ["main.py"] + list(args)
        with redirect_stdout(stdout), redirect_stderr(stderr), patch("sys.argv", argv):
            try:
                main()
            except SystemExit as exc:
                exit_code = exc.code
        return stdout.getvalue(), stderr.getvalue(), exit_code

    @patch("main.fetch_user_repos")
    @patch("main.fetch_user_profile")
    def test_cli_success_prints_summary_and_exports(
        self, mock_profile: MagicMock, mock_repos: MagicMock
    ) -> None:
        """A successful run prints the summary and exports JSON."""
        mock_profile.return_value = {
            "login": "octocat",
            "name": "The Octocat",
            "created_at": "2011-01-25T18:44:36Z",
            "followers": 1000,
        }
        mock_repos.return_value = [
            {
                "name": "r1",
                "language": "Python",
                "stargazers_count": 3,
                "forks_count": 1,
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "stats.json")
            stdout, _, code = self._run_cli(
                "octocat", "--json", out_path, "--top-langs", "1"
            )
            self.assertIsNone(code)
            self.assertIn("GITHUB PROFILE: The Octocat (@octocat)", stdout)
            self.assertIn("Successfully exported data to", stdout)
            data = json.loads(Path(out_path).read_text(encoding="utf-8"))
        self.assertEqual(data["metrics"]["total_stars"], 3)

    @patch("main.fetch_user_profile")
    def test_cli_unknown_user_exits_one(self, mock_profile: MagicMock) -> None:
        """Unresolvable profiles exit 1 with an error on stderr."""
        mock_profile.return_value = None
        _, stderr, code = self._run_cli("ghost-user")
        self.assertEqual(code, 1)
        self.assertIn("Could not retrieve profile for user 'ghost-user'", stderr)


if __name__ == "__main__":
    unittest.main()

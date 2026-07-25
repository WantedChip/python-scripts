"""Unit tests for GitHub User Info Fetcher."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import (
    analyze_languages,
    export_json,
    fetch_user_profile,
    fetch_user_repos,
    format_user_summary,
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


if __name__ == "__main__":
    unittest.main()

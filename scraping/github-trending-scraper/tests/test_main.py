"""Unit tests for GitHub Trending Scraper."""

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    Repository,
    build_parser,
    calculate_since_date,
    fetch_trending_via_api,
    format_markdown_table,
    format_terminal_table,
    main,
    parse_github_trending_html,
)


def _urlopen_result(payload: Any, status: int = 200) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    body = payload if isinstance(payload, str) else json.dumps(payload)
    resp.read.return_value = body.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


def _make_repo(**overrides: Any) -> Repository:
    """Create a fully-populated Repository with optional field overrides."""
    fields = dict(
        owner="psf",
        name="requests",
        full_name="psf/requests",
        url="https://github.com/psf/requests",
        description="Python HTTP for Humans.",
        language="Python",
        stars=50000,
        forks=9000,
    )
    fields.update(overrides)
    return Repository(**fields)


API_PAYLOAD = {
    "items": [
        {
            "owner": {"login": "psf"},
            "name": "requests",
            "full_name": "psf/requests",
            "html_url": "https://github.com/psf/requests",
            "description": "Python HTTP for Humans.",
            "language": "Python",
            "stargazers_count": 50000,
            "forks_count": 9000,
        },
        {
            "owner": {"login": "tokyo-night"},
            "name": "theme",
            "description": None,
            "language": None,
            "stargazers_count": 10,
            "forks_count": 2,
        },
    ]
}


class TestGitHubTrendingScraper(unittest.TestCase):
    """Test suite for date calculation, HTML parsing, and formatting functions."""

    def test_calculate_since_date(self) -> None:
        daily_date = calculate_since_date("daily")
        weekly_date = calculate_since_date("weekly")
        self.assertRegex(daily_date, r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(weekly_date, r"^\d{4}-\d{2}-\d{2}$")

    def test_format_markdown_table(self) -> None:
        repos = [
            Repository(
                owner="psf",
                name="requests",
                full_name="psf/requests",
                url="https://github.com/psf/requests",
                description="Python HTTP for Humans.",
                language="Python",
                stars=50000,
                forks=9000,
            )
        ]
        md = format_markdown_table(repos)
        self.assertIn("# GitHub Trending Repositories", md)
        self.assertIn("[psf/requests](https://github.com/psf/requests)", md)
        self.assertIn("50,000", md)

    def test_format_terminal_table(self) -> None:
        repos = [
            Repository(
                owner="torvalds",
                name="linux",
                full_name="torvalds/linux",
                url="https://github.com/torvalds/linux",
                description="Linux kernel source tree",
                language="C",
                stars=160000,
                forks=50000,
            )
        ]
        term = format_terminal_table(repos)
        self.assertIn("torvalds/linux", term)
        self.assertIn("160000", term)

    def test_parse_github_trending_html(self) -> None:
        html = """
        <html>
        <body>
        <article class="Box-row">
            <h2>
                <a href="/psf/black"> psf / black </a>
            </h2>
            <p class="col-9">The uncompromising Python code formatter.</p>
        </article>
        </body>
        </html>
        """
        repos = parse_github_trending_html(html)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0].owner, "psf")
        self.assertEqual(repos[0].name, "black")
        self.assertEqual(repos[0].full_name, "psf/black")
        self.assertIn("uncompromising Python code formatter", repos[0].description)


class TestSinceDateCalculation(unittest.TestCase):
    """Timeframe-to-date conversion."""

    def test_monthly_date_is_roughly_30_days_back(self) -> None:
        monthly = calculate_since_date("monthly")
        daily = calculate_since_date("daily")
        self.assertNotEqual(monthly, daily)
        self.assertLess(monthly, calculate_since_date("weekly"))

    def test_unknown_timeframe_falls_back_to_weekly(self) -> None:
        self.assertEqual(calculate_since_date("bogus"), calculate_since_date("weekly"))


class TestFetchTrendingViaApi(unittest.TestCase):
    """GitHub Search API client with mocked urlopen."""

    def test_fetch_success_maps_items_to_repositories(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            return_value=_urlopen_result(API_PAYLOAD),
        ) as mock_open:
            repos = fetch_trending_via_api(language="python", since="weekly", limit=5)
        self.assertEqual(len(repos), 2)
        first = repos[0]
        self.assertEqual(first.owner, "psf")
        self.assertEqual(first.full_name, "psf/requests")
        self.assertEqual(first.stars, 50000)
        second = repos[1]
        self.assertEqual(second.language, "Unspecified")
        self.assertEqual(second.description, "")
        url = mock_open.call_args.args[0].full_url
        self.assertIn("language%3Apython", url)
        self.assertIn("per_page=5", url)
        self.assertIn("sort=stars", url)

    def test_fetch_truncates_items_to_limit(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            return_value=_urlopen_result(API_PAYLOAD),
        ):
            repos = fetch_trending_via_api(limit=1)
        self.assertEqual(len(repos), 1)

    def test_fetch_non_200_returns_empty_list(self) -> None:
        resp = _urlopen_result(API_PAYLOAD, status=403)
        with patch("main.urllib.request.urlopen", return_value=resp):
            self.assertEqual(fetch_trending_via_api(), [])

    def test_fetch_network_error_returns_empty_list(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("rate limited"),
        ):
            self.assertEqual(fetch_trending_via_api(), [])

    def test_fetch_malformed_json_returns_empty_list(self) -> None:
        resp = _urlopen_result("<html>oops</html>")
        with patch("main.urllib.request.urlopen", return_value=resp):
            self.assertEqual(fetch_trending_via_api(), [])


class TestHtmlFallbackParser(unittest.TestCase):
    """HTML fallback parser edge cases."""

    def test_articles_without_owner_name_are_skipped(self) -> None:
        html = (
            "<article class='Box-row'><h2><a>Just a title</a></h2>"
            "<p class='col-9'>Some description.</p></article>"
        )
        self.assertEqual(parse_github_trending_html(html), [])

    def test_malformed_input_returns_empty_list(self) -> None:
        self.assertEqual(parse_github_trending_html(None), [])

    def test_description_and_language_defaults_applied(self) -> None:
        html = (
            "<article class='Box-row'><h2><a href='/a/b'> a / b </a></h2>" "</article>"
        )
        repos = parse_github_trending_html(html)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0].language, "Unspecified")
        self.assertEqual(repos[0].description, "")


class TestTableFormatting(unittest.TestCase):
    """Formatting edge cases for Markdown and terminal output."""

    def test_markdown_escapes_pipes_and_truncates_long_descriptions(self) -> None:
        repo = _make_repo(description="Uses | pipes and a very long description " * 4)
        md = format_markdown_table([repo])
        self.assertIn("Uses - pipes", md)
        self.assertIn("...", md)

    def test_markdown_renders_counts_with_thousands_separator(self) -> None:
        md = format_markdown_table([_make_repo(forks=1234567)])
        self.assertIn("1,234,567", md)

    def test_terminal_table_truncates_wide_columns(self) -> None:
        repo = _make_repo(
            full_name="a-very-long-owner-name/and-a-long-repository-name",
            language="Objective-C++",
            description="An extremely long description exceeding the column width!",
        )
        term = format_terminal_table([repo])
        self.assertIn("a-very-long-owner-name/and-a-l", term)
        self.assertIn("Objective-", term)
        self.assertIn("...", term)


class TestGithubTrendingCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def test_build_parser_defaults(self) -> None:
        args = build_parser().parse_args([])
        self.assertIsNone(args.language)
        self.assertEqual(args.since, "weekly")
        self.assertEqual(args.limit, 15)
        self.assertEqual(args.format, "markdown")

    def test_repository_to_dict_round_trip(self) -> None:
        as_dict = _make_repo().to_dict()
        self.assertEqual(as_dict["full_name"], "psf/requests")
        self.assertEqual(as_dict["stars"], 50000)

    def _run_main(self, argv: list) -> tuple:
        """Run main() capturing stdout/stderr; return (code, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_main_prints_json_to_stdout(self) -> None:
        with patch("main.fetch_trending_via_api", return_value=[_make_repo()]):
            code, out, _ = self._run_main(["--format", "json"])
        self.assertEqual(code, 0)
        payload: Any = json.loads(out)
        self.assertEqual(payload[0]["name"], "requests")

    def test_main_saves_terminal_output_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "trending.txt")
            with patch("main.fetch_trending_via_api", return_value=[_make_repo()]):
                code, out, _ = self._run_main(
                    ["--format", "terminal", "--output", out_path]
                )
            self.assertEqual(code, 0)
            self.assertIn(f"Trending repository list saved to {out_path}", out)
            with open(out_path, encoding="utf-8") as f:
                saved = f.read()
            self.assertIn("REPOSITORY", saved)
            self.assertIn("psf/requests", saved)

    def test_main_reports_api_failure(self) -> None:
        with patch("main.fetch_trending_via_api", return_value=[]):
            code, _, err = self._run_main(["--language", "python"])
        self.assertEqual(code, 1)
        self.assertIn("Could not retrieve data from GitHub Search API.", err)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for GitHub Trending Scraper."""

import unittest

from main import (
    Repository,
    calculate_since_date,
    format_markdown_table,
    format_terminal_table,
    parse_github_trending_html,
)


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


if __name__ == "__main__":
    unittest.main()

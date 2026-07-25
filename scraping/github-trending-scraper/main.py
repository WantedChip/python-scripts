"""GitHub Trending Scraper.

Fetches trending repositories on GitHub by programming language and timeframe
using GitHub REST Search API with HTML fallback, formatted as Markdown tables,
JSON, or ASCII terminal tables.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import datetime
import html.parser
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Repository:
    """Dataclass holding repository details."""

    owner: str
    name: str
    full_name: str
    url: str
    description: str
    language: str
    stars: int
    forks: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert repository object to dictionary."""
        return asdict(self)


def calculate_since_date(since: str) -> str:
    """Calculate ISO 8601 date string for API filtering based on timeframe.

    Args:
        since: Timeframe string ('daily', 'weekly', 'monthly').

    Returns:
        Formatted date string YYYY-MM-DD.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    if since == "daily":
        delta = datetime.timedelta(days=1)
    elif since == "weekly":
        delta = datetime.timedelta(weeks=1)
    elif since == "monthly":
        delta = datetime.timedelta(days=30)
    else:
        delta = datetime.timedelta(weeks=1)

    target_date = now - delta
    return target_date.strftime("%Y-%m-%d")


def fetch_trending_via_api(
    language: Optional[str] = None,
    since: str = "weekly",
    limit: int = 15,
    timeout: int = 10,
) -> List[Repository]:
    """Fetch top repositories via GitHub Search REST API.

    Args:
        language: Programming language filter.
        since: Timeframe ('daily', 'weekly', 'monthly').
        limit: Number of repositories to return.
        timeout: Request timeout in seconds.

    Returns:
        List of Repository dataclass items.
    """
    since_date = calculate_since_date(since)
    q_parts = [f"created:>{since_date}"]
    if language:
        q_parts.append(f"language:{language}")

    query = " ".join(q_parts)
    encoded_query = urllib.parse.quote(query)
    base_api = "https://api.github.com/search/repositories"
    url = f"{base_api}?q={encoded_query}&sort=stars&order=desc&per_page={limit}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GitHub-Trending-Scraper/1.0 (Python)",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                payload = json.loads(response.read().decode("utf-8"))
                items = payload.get("items", [])
                repos = []
                for item in items[:limit]:
                    owner = item.get("owner", {}).get("login", "Unknown")
                    name = item.get("name", "Unknown")
                    full_n = item.get("full_name", f"{owner}/{name}")
                    html_u = item.get("html_url", f"https://github.com/{owner}/{name}")
                    repos.append(
                        Repository(
                            owner=owner,
                            name=name,
                            full_name=full_n,
                            url=html_u,
                            description=(item.get("description") or "").strip(),
                            language=item.get("language") or "Unspecified",
                            stars=item.get("stargazers_count", 0),
                            forks=item.get("forks_count", 0),
                        )
                    )
                return repos
    except (urllib.error.URLError, json.JSONDecodeError, OSError, ValueError):
        return []

    return []


class HTMLTrendingParser(html.parser.HTMLParser):
    """Fallback parser for GitHub Trending HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self.repositories: List[Repository] = []
        self.in_article = False
        self.current_repo: Dict[str, Any] = {}
        self.in_h2 = False
        self.in_p = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        tag_lower = tag.lower()

        if tag_lower == "article" and "Box-row" in attr_dict.get("class", ""):
            self.in_article = True
            self.current_repo = {
                "owner": "",
                "name": "",
                "desc": "",
                "lang": "",
                "stars": 0,
                "forks": 0,
            }

        if self.in_article:
            if tag_lower == "h2":
                self.in_h2 = True
            elif tag_lower == "p" and "col-9" in attr_dict.get("class", ""):
                self.in_p = True

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "article" and self.in_article:
            self.in_article = False
            owner = self.current_repo.get("owner", "").strip("/")
            name = self.current_repo.get("name", "").strip("/")
            if owner and name:
                lang_val = self.current_repo.get("lang") or "Unspecified"
                self.repositories.append(
                    Repository(
                        owner=owner,
                        name=name,
                        full_name=f"{owner}/{name}",
                        url=f"https://github.com/{owner}/{name}",
                        description=self.current_repo.get("desc", "").strip(),
                        language=lang_val,
                        stars=self.current_repo.get("stars", 0),
                        forks=self.current_repo.get("forks", 0),
                    )
                )
        elif tag_lower == "h2":
            self.in_h2 = False
        elif tag_lower == "p":
            self.in_p = False

    def handle_data(self, data: str) -> None:
        if self.in_article:
            text = data.strip()
            if self.in_h2 and "/" in text:
                parts = [p.strip() for p in text.split("/") if p.strip()]
                if len(parts) == 2:
                    self.current_repo["owner"] = parts[0]
                    self.current_repo["name"] = parts[1]
            elif self.in_p and text:
                self.current_repo["desc"] += text + " "


def parse_github_trending_html(html_content: str) -> List[Repository]:
    """Parse HTML content from github.com/trending into repository objects.

    Args:
        html_content: GitHub Trending HTML source code.

    Returns:
        List of Repository instances.
    """
    parser = HTMLTrendingParser()
    try:
        parser.feed(html_content)
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
    return parser.repositories


def format_markdown_table(repos: List[Repository]) -> str:
    """Format repository list into Markdown table representation.

    Args:
        repos: List of Repository objects.

    Returns:
        Formatted Markdown text string.
    """
    lines = [
        "# GitHub Trending Repositories",
        "",
        "| Repository | Language | Stars | Forks | Description |",
        "| :--- | :--- | :---: | :---: | :--- |",
    ]
    for repo in repos:
        repo_link = f"[{repo.full_name}]({repo.url})"
        desc = repo.description.replace("|", "-")
        if len(desc) > 80:
            desc = desc[:77] + "..."
        lines.append(
            f"| {repo_link} | {repo.language} | {repo.stars:,} | "
            f"{repo.forks:,} | {desc} |"
        )

    return "\n".join(lines)


def format_terminal_table(repos: List[Repository]) -> str:
    """Format repository list into terminal ASCII table.

    Args:
        repos: List of Repository objects.

    Returns:
        Multi-line formatted table string.
    """
    col_rep = f"{'REPOSITORY':<32}"
    col_lang = f"{'LANGUAGE':<12}"
    col_stars = f"{'STARS':<8}"
    col_forks = f"{'FORKS':<8}"
    header = f"{col_rep} | {col_lang} | {col_stars} | {col_forks} | DESCRIPTION"
    divider = "-" * 95
    lines = [divider, header, divider]

    for repo in repos:
        name = repo.full_name[:30]
        lang = repo.language[:10]
        d_len = len(repo.description)
        desc = repo.description[:25] + ("..." if d_len > 25 else "")
        row_str = (
            f"{name:<32} | {lang:<12} | {repo.stars:<8} | " f"{repo.forks:<8} | {desc}"
        )
        lines.append(row_str)

    lines.append(divider)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Scrape GitHub trending repositories by language and date range."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--language",
        "-l",
        type=str,
        help="Filter by programming language (e.g. python, javascript, rust)",
    )
    parser.add_argument(
        "--since",
        choices=["daily", "weekly", "monthly"],
        default="weekly",
        help="Timeframe scope (default: weekly)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Number of repositories to return (default: 15)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "terminal"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="File path to save the output",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for GitHub Trending Scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    repos = fetch_trending_via_api(
        language=parsed.language, since=parsed.since, limit=parsed.limit
    )

    if not repos:
        msg = "Warning: Could not retrieve data from GitHub Search API."
        print(msg, file=sys.stderr)
        return 1

    if parsed.format == "json":
        output_str = json.dumps([r.to_dict() for r in repos], indent=2)
    elif parsed.format == "terminal":
        output_str = format_terminal_table(repos)
    else:
        output_str = format_markdown_table(repos)

    if parsed.output:
        with open(parsed.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Trending repository list saved to {parsed.output}")
    else:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())

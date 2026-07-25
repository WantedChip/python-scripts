#!/usr/bin/env python3
"""GitHub User Info Fetcher script.

Fetches GitHub user profile metrics, public repo count, top language breakdown,
and total stars.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, cast

GITHUB_API_BASE = "https://api.github.com"


def fetch_json(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Fetch JSON response from GitHub REST API URL.

    Args:
        url: API endpoint URL string.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response payload or None on failure.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GitHubUserInfoFetcher/1.0 (Python)",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                return cast(Dict[str, Any], json.loads(response.read().decode("utf-8")))
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error fetching {url}: {err}", file=sys.stderr)
    return None


def fetch_user_profile(username: str) -> Optional[Dict[str, Any]]:
    """Fetch GitHub user profile metadata dictionary.

    Args:
        username: Target GitHub username string.

    Returns:
        User profile dictionary or None on failure.
    """
    user_clean = urllib.parse.quote(username.strip())
    url = f"{GITHUB_API_BASE}/users/{user_clean}"
    return fetch_json(url)


def fetch_user_repos(username: str, per_page: int = 100) -> List[Dict[str, Any]]:
    """Fetch user's public repositories list from GitHub API.

    Args:
        username: Target GitHub username string.
        per_page: Maximum repositories per API page (default: 100).

    Returns:
        List of repository dictionaries.
    """
    user_clean = urllib.parse.quote(username.strip())
    url = f"{GITHUB_API_BASE}/users/{user_clean}/repos?per_page={per_page}&sort=updated"
    data = fetch_json(url)
    return data if isinstance(data, list) else []


def calculate_total_stars(repos: List[Dict[str, Any]]) -> int:
    """Calculate aggregate stargazers count across all user public repositories.

    Args:
        repos: List of repository dictionaries.

    Returns:
        Total star count integer.
    """
    return sum(repo.get("stargazers_count", 0) for repo in repos)


def analyze_languages(repos: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
    """Compute repository count frequency per primary programming language.

    Args:
        repos: List of repository dictionaries.

    Returns:
        Sorted list of tuples (language string, repo count int) descending.
    """
    lang_counts: Dict[str, int] = {}
    for repo in repos:
        lang = repo.get("language")
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

    return sorted(lang_counts.items(), key=lambda item: item[1], reverse=True)


def format_user_summary(
    profile: Dict[str, Any], repos: List[Dict[str, Any]], top_langs_count: int = 5
) -> str:
    """Format user profile stats and repository insights into a terminal summary card.

    Args:
        profile: GitHub user profile dictionary.
        repos: List of public repositories.
        top_langs_count: Max number of top languages to display.

    Returns:
        Formatted ASCII string representation of profile summary.
    """
    # pylint: disable=too-many-locals
    name = profile.get("name") or profile.get("login", "Unknown")
    login = profile.get("login", "")
    bio = (profile.get("bio") or "No bio provided.").strip().replace("\n", " ")
    company = profile.get("company") or "N/A"
    location = profile.get("location") or "N/A"
    followers = profile.get("followers", 0)
    following = profile.get("following", 0)
    public_repos = profile.get("public_repos", 0)
    public_gists = profile.get("public_gists", 0)
    created_at = profile.get("created_at", "N/A")[:10]
    html_url = profile.get("html_url", "")

    total_stars = sum(r.get("stargazers_count", 0) for r in repos)
    total_forks = sum(r.get("forks_count", 0) for r in repos)

    languages = analyze_languages(repos)
    lang_str_list = [f"{lang} ({cnt})" for lang, cnt in languages[:top_langs_count]]
    top_langs_formatted = ", ".join(lang_str_list) if lang_str_list else "None detected"

    lines = [
        "==================================================",
        f"  GITHUB PROFILE: {name} (@{login})",
        "==================================================",
        f"  Username   : @{login}",
        f"  Bio        : {bio[:60]}{'...' if len(bio) > 60 else ''}",
        f"  Company    : {company}",
        f"  Location   : {location}",
        f"  Joined     : {created_at}",
        f"  Profile    : {html_url}",
        "--------------------------------------------------",
        "  STATS:",
        f"  • Followers     : {followers}",
        f"  • Following     : {following}",
        f"  • Public Repos  : {public_repos}",
        f"  • Public Gists  : {public_gists}",
        f"  • Total Stars   : {total_stars}",
        f"  • Total Forks   : {total_forks}",
        "--------------------------------------------------",
        f"  Top Languages : {top_langs_formatted}",
        "==================================================",
    ]
    return "\n".join(lines)


def export_json(
    profile: Dict[str, Any], repos: List[Dict[str, Any]], filepath: str
) -> bool:
    """Export profile and repository statistics to a JSON file.

    Args:
        profile: Profile dictionary.
        repos: List of repositories.
        filepath: Path to output JSON file.

    Returns:
        True if success, False otherwise.
    """
    top_langs = dict(analyze_languages(repos))
    payload = {
        "user": {
            "login": profile.get("login"),
            "name": profile.get("name"),
            "bio": profile.get("bio"),
            "company": profile.get("company"),
            "location": profile.get("location"),
            "followers": profile.get("followers"),
            "following": profile.get("following"),
            "public_repos": profile.get("public_repos"),
            "public_gists": profile.get("public_gists"),
            "created_at": profile.get("created_at"),
            "html_url": profile.get("html_url"),
        },
        "metrics": {
            "total_stars": sum(r.get("stargazers_count", 0) for r in repos),
            "total_forks": sum(r.get("forks_count", 0) for r in repos),
            "languages": top_langs,
        },
        "repositories": [
            {
                "name": r.get("name"),
                "language": r.get("language"),
                "stars": r.get("stargazers_count"),
                "forks": r.get("forks_count"),
                "url": r.get("html_url"),
            }
            for r in repos
        ],
    }

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return True
    except OSError as err:
        print(f"Error saving JSON export to {filepath}: {err}", file=sys.stderr)
        return False


def main() -> None:
    """Main CLI entrypoint for GitHub User Info Fetcher."""
    parser = argparse.ArgumentParser(
        description="Fetch GitHub user profile stats and repository insights."
    )
    parser.add_argument("username", help="GitHub username to inspect")
    parser.add_argument("--json", "-j", help="Output filepath for JSON export")
    parser.add_argument(
        "--top-langs",
        type=int,
        default=5,
        help="Number of top languages to summarize (default: 5)",
    )

    args = parser.parse_args()

    print(f"Fetching GitHub user profile for '@{args.username}'...")
    profile = fetch_user_profile(args.username)
    if not profile:
        print(
            f"Could not retrieve profile for user '{args.username}'.", file=sys.stderr
        )
        sys.exit(1)

    print("Fetching public repository data...")
    repos = fetch_user_repos(args.username)

    summary = format_user_summary(profile, repos, top_langs_count=args.top_langs)
    print(summary)

    if args.json:
        if export_json(profile, repos, args.json):
            print(f"Successfully exported data to {args.json}")


if __name__ == "__main__":
    main()

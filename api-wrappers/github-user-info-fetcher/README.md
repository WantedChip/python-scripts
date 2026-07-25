# GitHub User Info Fetcher

A Python CLI tool to fetch GitHub user profiles, repository counts, language breakdowns, and activity metrics via the GitHub REST API.

## Features
- Fetches user metadata (bio, location, company, followers/following, join date).
- Analyzes public repositories to compute total stars, forks, and top programming languages.
- Terminal profile card display.
- Exports profile & repository statistics to JSON.

## Usage

```bash
# Fetch profile summary for user
python main.py torvalds

# Customize number of top languages displayed
python main.py octocat --top-langs 3

# Export user data and repos to JSON
python main.py psf --json psf_stats.json
```

# Secret Deleted or Not

A Git history audit tool designed to verify whether a deleted secret/API key still resides somewhere in historical commits, branches, stashes, or reflogs after deletion from HEAD.

## Features

- **Pickaxe Search**: Uses `git log -S` and `git log -G` to track exact additions/deletions of secrets across all branches.
- **Stash Inspection**: Scans active git stashes for uncommitted leaks.
- **Reflog Audit**: Checks git reflog entries for commits that were detached or reset.
- **Structured Reports**: Supports human-readable output and JSON reporting.

## Usage

```bash
# Search for an exact secret string in current directory git repo
python main.py --secret "AWS_SECRET_KEY_12345" --repo /path/to/repo

# Regex pattern search with JSON output
python main.py --secret "AKIA[0-9A-Z]{16}" --regex --json
```

## Running Tests

```bash
python -m unittest discover -s tests
```

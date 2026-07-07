# Git Repo Cleanup Tool

Analyzes a git repository for bloat, stale branches, untracked junk, and accidentally committed secrets.

## Features

- **Large File Detection**: Lists all tracked files exceeding a configurable size threshold.
- **Stale Branch Finder**: Flags local branches that are merged into HEAD or haven't had a commit in N days.
- **Untracked & Ignored File Scanner**: Lists files not tracked by git (untracked) or matched by `.gitignore` but still present on disk.
- **Secret Scanner**: Scans recent commit diffs for:
  - Known secret patterns (AWS keys, GitHub tokens, private keys, API keys, etc.)
  - High-entropy tokens (configurable Shannon entropy threshold)
  - All matched values are **masked/redacted** in output — no secrets are printed.

## Requirements

No third-party dependencies. Requires Python 3.9+ and `git` on PATH.

## Usage

```bash
# Analyze the current directory
python git_cleanup.py

# Analyze a specific repository
python git_cleanup.py --repo /path/to/repo

# Adjust thresholds
python git_cleanup.py --large-file-kb 1000 --stale-days 60 --max-commits 100

# Skip secret scanning (faster)
python git_cleanup.py --skip-secrets

# Verbose output
python git_cleanup.py -v
```

## Options

| Argument | Description | Default |
|---|---|---|
| `--repo PATH` | Path to the git repository | `.` (current dir) |
| `--large-file-kb KB` | Flag files larger than this size in KB | 500 |
| `--stale-days DAYS` | Flag branches inactive for this many days | 90 |
| `--max-commits N` | Number of recent commits to scan for secrets | 50 |
| `--entropy-threshold FLOAT` | Shannon entropy threshold for token detection | 4.5 |
| `--skip-secrets` | Skip the secret scanning step | False |
| `-v, --verbose` | Enable verbose logging | False |

## Notes

- Secret patterns match common formats (AWS, GitHub, Stripe, Google, Slack, private keys).
- Secret values are **always masked** in output — only the pattern name, commit SHA, file, and line number are shown.
- The tool only reads the repository; it makes **no modifications** to files, branches, or history.
- To remove a secret from history, use `git filter-repo` or BFG Repo-Cleaner.

## Running Tests

```bash
pytest
```

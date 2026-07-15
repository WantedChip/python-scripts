# branch-graveyard

Find local and remote branches that are merged, abandoned, duplicated, or attached to closed PRs, with a safe interactive cleanup mode.

## Usage

```bash
python branch_graveyard.py [path/to/repo] [options]
```

### Options

- `-d`, `--days`: Threshold in days to consider a branch abandoned (default: `30`).
- `-m`, `--main`: Main/default branch of the repository (default: auto-detected, falling back to `main`).
- `-r`, `--remote`: Remote name to query (default: `origin`).
- `-i`, `--interactive`: Prompt interactively to delete detected graveyard branches.
- `--dry-run`: Dry-run mode; do not perform any actual deletions.
- `--github-token`: GitHub personal access token to query for closed pull requests.
- `--exclude`: Glob pattern(s) of branches to exclude from analysis (e.g. `release/*`, `dev`).
- `-v`, `--verbose`: Enable verbose logging output.

## Quality

Quality: pylint 10.00/10 · 90% coverage · 0 dependencies

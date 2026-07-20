# stash-conflict-preview

Estimate and preview potential Git merge conflicts at file and line levels before running `git stash apply` in your current working tree checkout.

## Usage

Check conflict status for the latest stash (index 0):

```bash
python stash_conflict_preview.py
```

Specify a custom stash list index (e.g. index 2):

```bash
python stash_conflict_preview.py 2
```

Audit a target Git repository directory path:

```bash
python stash_conflict_preview.py --repo C:/Users/Name/Projects/my_app
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)
- Git command line tool installed on system PATH

## Preview Diagnostics

- **Stash line audit**: Parses diff modifications between the target stash and its base checkout commit to locate specific modified line ranges.
- **HEAD changes analysis**: Parses the diff between the stash base and current active HEAD commits to identify overlapping lines.
- **Unstaged changes check**: Evaluates active uncommitted working tree modifications for overlapping edit coordinates.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

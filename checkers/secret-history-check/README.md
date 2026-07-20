# secret-history-check

Check whether a secret or keyword search term has been completely removed or if it still exists in your Git repository commit history database.

## Usage

Scan the Git commit history of the current repository for common secret definitions (e.g. AWS access keys, GitHub tokens, private key headers):

```bash
python secret_history_check.py
```

Audit a custom target repository path:

```bash
python secret_history_check.py C:/Users/Name/Projects/my_repo
```

Search Git diffs for a specific deleted secret string or keyword:

```bash
python secret_history_check.py --query "my_secret_token_12345"
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)
- Git command-line client installed on the system PATH

## Scans Performed

- Parses historical diff logs across all branches (`git log -p --all --unified=0`) via subprocess.
- Scans line additions in commit patches for common patterns (AWS IDs, private key signatures, GitHub tokens, user passwords).
- Identifies matching commit hash, author, commit date, file path, and matching code line string.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

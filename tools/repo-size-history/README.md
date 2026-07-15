# repo-size-history

Show exactly when a repository became bloated and which commits/files caused the growth by analyzing tracked file sizes over history.

## Usage

```bash
python repo_size_history.py [path/to/repo] [options]
```

### Options

- `-n`, `--limit`: Max number of commits to analyze (default: `50`).
- `-s`, `--spike-threshold`: Percentage increase in repository size to flag as a spike (default: `10.0` for 10%).
- `-f`, `--file-size-mb`: Flag individual files larger than this threshold in MB (default: `5.0`).
- `--tags-only`: Analyze only tagged commits rather than every commit.
- `-v`, `--verbose`: Enable verbose logging output.

## Quality

Quality: pylint 10.00/10 · 90% coverage · 0 dependencies

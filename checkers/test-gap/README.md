# Test Gap

Identify test coverage gaps by comparing line-level code modifications in Git diff against test execution results from a `.coverage` database.

## Usage

```bash
python test_gap.py --ref origin/main --cov-file .coverage
```

### Options

- `--diff-file`: Use a pre-saved diff file path rather than executing a live git diff.
- `--ref`: Git reference to compare against (e.g. branch name, tag, commit SHA).
- `--cov-file`: Custom path to a coverage data file (defaults to `.coverage` in active directory).
- `--format`: Format of the stdout report, either `text` (default) or `markdown`.

## Requirements

- `coverage==7.15.0`

## Notes

- Standard git command outputs are analyzed relative to the repository base directory.
- Filters out non-python files and reports line-by-line coverage discrepancies, returning a non-zero exit code if gaps are found.

Quality: pylint 10.00/10 · 100% coverage · 1 dependencies

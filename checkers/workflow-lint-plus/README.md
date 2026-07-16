# Workflow Lint Plus

An advanced linter for GitHub Actions CI workflow files. Flags potential problems beyond simple syntax validation, such as duplicate jobs, unpinned third-party actions, impossible run conditions, unnecessary matrix keys, missing timeouts, and cache configuration errors.

## Usage

```bash
python workflow_lint_plus.py ../../.github/workflows
```

### Options

- `paths`: List of files or directories to inspect. Defaults to `.github/workflows`.

## Requirements

- `PyYAML==6.0.1`

## Notes

- Verifies SHA-1 tag pinning on third-party actions.
- Detects combinations like `success() && failure()` in GHA conditions.
- Flags missing timeouts at job and step levels.

Quality: pylint 10.00/10 · 100% coverage · 1 dependencies

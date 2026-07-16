# CI Local

Translate GitHub Actions workflow files into local shell commands and executable scripts to reproduce CI runs locally.

## Usage

```bash
python ci_local.py --workflow ../../.github/workflows/ci.yml --job quality-gate --matrix "os=windows-latest,python-version=3.12"
```

### Options

- `--workflow`: Path to the YAML workflow file (default: `.github/workflows/ci.yml`).
- `--job`: The GHA job name to analyze and reproduce (e.g., `quality-gate`). If omitted, lists available jobs.
- `--matrix`: Comma-separated overrides for matrix configurations.

## Requirements

- `PyYAML==6.0.1`

## Notes

- GHA specific environment variables and third-party actions are mapped or marked as skipped.
- Generates a local shell script (`reproduce_<job_name>.sh` or `reproduce_<job_name>.ps1` depending on the system OS).

Quality: pylint 10.00/10 · 100% coverage · 1 dependencies

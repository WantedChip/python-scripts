# Flaky Test Hunter

Find and rank flaky tests by repeatedly running a pytest suite in randomized order and with optional random timing delays.

## Usage

```bash
python flaky_test_hunter.py tests --iterations 10 --min-delay 0.001 --max-delay 0.05
```

### Options

- `target`: Path to the test file or directory (default: `tests`).
- `--iterations`: Number of execution rounds to run (default: `5`).
- `--min-delay`: Minimum setup delay to inject (default: `0.0` seconds).
- `--max-delay`: Maximum setup delay to inject (default: `0.0` seconds).
- `--pytest-path`: Path to specify a custom pytest binary.

## Requirements

- `pytest`

## Notes

- Uses a dynamic, auto-cleanup pytest plugin to intercept test loading, shuffle execution list, inject random delays, and track outcomes.

Quality: pylint 10.00/10 · 100% coverage · 1 dependencies

# CI Failure Deduper

Analyze multiple CI log files, extract traceback/error sections, normalize variable parts (line numbers, addresses, timestamps, file paths), and group matching failures by their root cause.

## Usage

```bash
python ci_failure_deduper.py log1.txt log2.txt --format markdown
```

### Options

- `logs`: Log files or glob pattern (e.g. `logs/*.log`).
- `--dir`: Directory path containing logs to scan recursively.
- `--format`: Output format, either `text` (default) or `markdown`.

## Requirements

- Standard Library only

## Notes

- Detects Python stack traces, Pytest assertion failures, linter/compiler failures, and generic log entries containing `ERROR`/`FATAL`.

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

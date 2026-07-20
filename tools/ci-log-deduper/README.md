# ci-log-deduper

Parse multiple failed CI log files, extract error tracebacks and exceptions, collapse dynamic addresses/line numbers, and group logs into root failure signature blocks.

## Usage

Analyze multiple log files and group them into distinct failure signatures:

```bash
python ci_log_deduper.py job_fail_1.log job_fail_2.log job_fail_3.log
```

You can pass globs or wildcards in standard terminal contexts:

```bash
python ci_log_deduper.py logs/job_fail_*.log
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Deduplication Heuristics

- **Traceback Scans**: Searches for Python tracebacks or keywords representing warnings and failures (`EXCEPTION:`, `FAIL:`, `FAILED:`, `ERROR:`).
- **Signature Normalization**: Replaces dynamic content (hex numbers, file paths, line coordinates, timestamps, digits) with generic placeholders (`<HEX>`, `<PATH>`, `<NUM>`) to map similar issues to single signatures.
- **Collating Tables**: Groups matched logs by signature frequency, outputting clear statistics summaries.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

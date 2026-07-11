# Cron Job Health Checker

A CLI schedule auditing utility to scan cron log entries, identify execution status failures, trace overlapping runs, highlight stuck jobs, and detect missed runs.

## Features

- **Execution Issue Analysis**:
  - **FAILURE**: Identifies runs terminating with errors or non-zero exit codes.
  - **OVERLAP**: Flags concurrent runs of the same job (starting before a preceding run ends).
  - **STUCK**: Highlights jobs remaining active beyond a customizable threshold.
  - **MISSED**: Simulates cron trigger patterns to spot silent/skipped executions.
- **Native Cron Step Simulator**: Parses standard crontab patterns (wildcards, step intervals, lists, ranges) natively with zero third-party dependencies.
- **Reporting Styles**: Outputs a structured report directly to the terminal, or writes a JSON database report.
- **Zero Dependencies**: Relies exclusively on Python's standard library.

## Log Entry Format

The utility expects standard timestamped logs in the following layout:

```text
2026-07-11 12:00:00 - job_name - START
2026-07-11 12:02:15 - job_name - END - SUCCESS
2026-07-11 12:05:00 - job_name - START
2026-07-11 12:06:30 - job_name - END - ERROR - exit code 1
```

## Usage

```bash
# Run a health audit on a cron log file
python cron_health_checker.py -i cron.log

# Audit logs and check for missed runs against expected cron schedules
python cron_health_checker.py -i cron.log -s schedules.json

# Save health analysis results to a JSON file
python cron_health_checker.py -i cron.log -s schedules.json -o report.json

# Set stuck threshold to 30 minutes (default: 60)
python cron_health_checker.py -i cron.log -t 30
```

## Schedules JSON Format

```json
{
  "backup-job": "0 2 * * *",
  "sync-data": "*/10 * * * *"
}
```

## Requirements

- Python 3.x (standard library only)

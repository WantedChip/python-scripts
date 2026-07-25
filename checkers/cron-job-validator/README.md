# Cron Job Validator & Conflict Detector

A Python command-line utility to validate crontab expression syntax (5/6-field), calculate future run schedules, and detect overlapping job runs.

## Features
- Full field validation (minute, hour, day of month, month, day of week).
- Range, step, list, and month/weekday name parsing (`JAN-DEC`, `MON-FRI`).
- Computes upcoming run timestamps.
- Conflict analysis across multiple cron schedules over a target time window.
- JSON output option (`--json`).

## Installation & Requirements
Standard Python 3.8+ standard library. No external dependencies required.

## Usage
```bash
python main.py "0 0 * * *" "*/30 * * * *" --check-conflicts --next-count 3
```

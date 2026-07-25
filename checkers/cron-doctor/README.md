# Cron Doctor

`cron-doctor` is a health diagnostic tool for crontabs, systemd timers, and scheduled task configurations.

## Features

- **Missing Executable Detection**: Verifies commands exist on system `PATH` or at specified absolute locations.
- **Stale Script Check**: Ensures referenced script targets (`.sh`, `.py`) actually exist.
- **Silent Failure Prevention**: Warns on cron commands missing `2>&1` or stderr log redirection.
- **Overlapping Run Detection**: Highlights high-frequency schedules lacking lock file mechanisms (`flock`).

## Usage

```bash
# Audit a crontab file
python main.py --file /etc/crontab

# Audit a single cron expression string
python main.py --entry "* * * * * /usr/bin/python3 /opt/backup.py"
```

## Running Tests

```bash
python -m unittest discover -s tests
```

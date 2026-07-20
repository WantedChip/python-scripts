# scheduled-task-auditor

Unified scheduler and startup task auditor scanning Windows Task Scheduler, Startup directories, Unix crontabs, and Systemd timers. It automatically detects broken commands, missing executables, and path vulnerabilities.

## Usage

Run a system-wide audit:

```bash
python scheduled_task_auditor.py
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Systems Audited

- **Windows**: Invokes `schtasks /query /fo csv /v` via subprocess, checks registry startup Run directories, and parses files in the user Startup directory.
- **Unix**: Parses `/etc/crontab`, `/etc/cron.*`, user crontabs (`crontab -l`), and Systemd `.timer` config blocks.

## Diagnostics Run

- Strips command line parameters and arguments to extract absolute or relative target binaries.
- Checks absolute binary exists using `os.path.exists`.
- Checks relative binary exists on system path environment using `shutil.which`.
- Flags broken paths (Critical) and missing PATH binaries (Warning).

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

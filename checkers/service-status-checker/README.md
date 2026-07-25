# Service Status Checker

A Python script that checks whether specified systemd services or process names are running, with optional auto-restart capability.

## Features

- Inspects systemd services using `systemctl` or fallback process scanning via `psutil`
- Reports PIDs and current status (`RUNNING`, `STOPPED`, `RESTARTED`)
- Optional `--restart` flag to attempt auto-restarting stopped services
- Outputs health status reports to console and JSON format

## Usage

```bash
python main.py nginx sshd postgresql
python main.py nginx redis-server --restart
python main.py python --output-json service_health.json
```

## Running Tests

```bash
python -m unittest discover -s tests
```

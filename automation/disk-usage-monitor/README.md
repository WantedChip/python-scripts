# Disk Usage Monitor

Monitors disk space usage across storage mounts and generates warning logs or JSON reports when free space falls below a specified threshold percentage.

## Features

- Scans system mount points/drives
- Calculates total, used, free space in GB and percentages
- Configurable free-space threshold percentage (default 15%)
- Logs warning alerts to console and optional log file
- Option to export diagnostic reports to JSON

## Usage

```bash
python main.py
python main.py --threshold 20.0
python main.py --mount / --threshold 10.0 --log-file alerts.log --output-json report.json
```

## Running Tests

```bash
python -m unittest discover -s tests
```

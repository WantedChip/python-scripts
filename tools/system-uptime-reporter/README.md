# System Uptime Reporter

A Python script that calculates system uptime, boot timestamp, and system load averages, outputting formatted summaries or JSON structures.

## Features
- Calculates system boot time using `psutil` or native OS APIs (`/proc/uptime`, Windows `GetTickCount64`).
- Formats uptime nicely into days, hours, minutes, and seconds.
- Captures system load averages (or CPU usage fallback).
- JSON export mode (`--json`).

## Requirements
```bash
pip install -r requirements.txt
```

## Usage
```bash
python main.py --json
```

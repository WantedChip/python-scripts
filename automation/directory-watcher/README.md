# Directory Watcher Script

A Python tool for real-time filesystem directory event monitoring (creation, modification, deletion) with timestamp logging and extension filtering.

## Features
- Real-time event notifications (`CREATED`, `MODIFIED`, `DELETED`).
- Extension filtering (e.g. `--extensions .py .json`).
- Supports both `watchdog` library engine and built-in standard library polling watcher.
- Optional log file persistence (`--log-file`).

## Installation & Requirements
```bash
pip install -r requirements.txt
```

## Usage
```bash
python main.py /path/to/directory -e .py .txt -l watcher.log
```

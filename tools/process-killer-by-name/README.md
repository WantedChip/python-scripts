# Process Killer by Name / Pattern

A Python command-line tool to find and terminate processes matching regex patterns or PID lists with dry-run safety modes and interactive prompts.

## Features
- Regex pattern matching on process names and command-line arguments.
- Direct filtering by target process PIDs (`--pids`).
- Dry-run simulation mode (`-d / --dry-run`).
- Choice between graceful termination (`SIGTERM`) and forced termination (`-f / --force / SIGKILL`).
- Interactive confirmation prompt with optional auto-yes flag (`-y / --yes`).

## Requirements
```bash
pip install -r requirements.txt
```

## Usage
```bash
python main.py -p "python.*" --dry-run
python main.py --pids 1234 5678 -f -y
```

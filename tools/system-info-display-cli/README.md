# System Info Display CLI

A command-line tool written in Python to display system metrics (OS details, CPU load, Memory, Disk usage, Uptime, and Top Processes) in a terminal dashboard or as JSON data.

## Features
- **Dashboard Display**: Clean ASCII terminal UI with usage bar charts.
- **JSON Export**: Export raw system stats for scripts and monitoring tools.
- **Top Processes**: Displays highest CPU-consuming processes.
- **Robust Fallback**: Uses `psutil` if available, falls back gracefully to Python standard library modules.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Terminal ASCII Dashboard
python main.py

# JSON Export
python main.py --json

# Show top 10 processes
python main.py --top-processes 10
```

## Running Tests

```bash
python -m unittest discover -s tests
```

# Task Time Tracker CLI

Command-line task time tracker with start/stop/switch commands, project tagging, summary reports, and CSV exports.

## Features
- **Task Timer**: Start, stop, or switch active tasks with project tagging.
- **Active Status Check**: Displays current active task, start time, and elapsed duration.
- **Duration Calculation**: Accurately measures time spent on completed and active sessions.
- **Aggregated Reports**: View daily, weekly, or overall time breakdowns by project and task.
- **CSV Export**: Export time records to CSV format.

## Usage

```bash
# Start a task timer
python main.py start "Write documentation" --project "Frontend"

# Check active task status
python main.py status

# Switch to a different task (stops active task automatically)
python main.py switch "Code review" --project "Backend"

# Stop current active task
python main.py stop

# View daily summary report
python main.py report --period daily

# View weekly summary report
python main.py report --period weekly

# Export all time logs to CSV
python main.py export --output report.csv
```

## Running Tests

```bash
python -m unittest discover -s tests
```

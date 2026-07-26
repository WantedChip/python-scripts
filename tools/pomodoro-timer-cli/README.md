# Pomodoro Timer CLI

A lightweight terminal Pomodoro timer with customizable work/break intervals, ASCII progress bar, audio notification beep, and JSON session history tracking.

## Features

- Live ASCII progress bar with time readout.
- Customizable work and break interval lengths.
- Multi-cycle execution.
- Terminal bell (`\a`) notification sound upon interval completion.
- Persistent session logging and statistical summary reporting.

## Usage

```bash
# Start a 25 min work / 5 min break Pomodoro cycle
python main.py start --work 25 --break 5 --cycles 4

# Run in test mode (accelerated timer)
python main.py start --work 5 --break 2 --test-mode

# View aggregate stats
python main.py stats
```

## Requirements

Python 3.8+ (Standard Library only).

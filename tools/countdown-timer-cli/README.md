# Countdown Timer CLI

A feature-rich command-line countdown timer with visual progress bar, audio completion notification, preset timers, and non-interactive script mode.

## Features
- **Flexible Duration Parsing**: Supports input like `10m`, `1h30s`, `45s`, `2h15m30s`, or raw seconds.
- **Preset Support**: Pre-configured timers (`pomodoro`, `short-break`, `long-break`, `tea`, `egg`).
- **Terminal Progress Bar**: Animated progress updates.
- **Completion Alert**: Terminal bell beep (`\a`) and customizable alarm text.
- **Non-Interactive Mode**: Instant calculation mode for automation and scripts.

## Usage

```bash
# Start a custom timer
python main.py --duration 10m

# Start a preset timer
python main.py --preset pomodoro

# List available presets
python main.py --list-presets

# Non-interactive mode (for scripts)
python main.py --duration 5s --non-interactive
```

## Running Tests
```bash
python -m unittest discover tests
```

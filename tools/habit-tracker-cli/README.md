# Habit Tracker CLI

A terminal-based habit tracker with daily check-ins, current and longest streak calculations, completion rate metrics, and ASCII calendar visualizations.

## Features
- **Habit Management**: Create, list, inspect, and delete habits.
- **Daily Check-ins**: Log completions for today or past dates.
- **Streak Calculation**: Computes current consecutive days streak and all-time longest streak.
- **ASCII Visualizations**: Weekly progress matrix table and monthly ASCII calendar grid.

## Usage

```bash
# Add a new habit
python main.py add "Exercise" --description "30 mins workout daily"

# Check in for today
python main.py checkin "Exercise"

# View all habit stats and streaks
python main.py stats

# Display monthly calendar grid
python main.py calendar "Exercise" --month 7 --year 2026

# Display weekly summary table
python main.py weekly
```

## Running Tests
```bash
python -m unittest discover tests
```

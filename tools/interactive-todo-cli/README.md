# Interactive TODO CLI Manager

A feature-rich terminal task manager built with SQLite persistence.

## Features

- Full task CRUD operations.
- Priority management: High, Medium, Low.
- Tag tagging and tag-based filtering.
- Status filtering (`pending`, `completed`, `archived`, `all`).
- ASCII table formatting output.

## Usage

```bash
# Add a task
python main.py add "Finish project documentation" -p High -t work,docs

# List pending tasks
python main.py list

# Filter tasks by tag
python main.py list -t work

# Mark task as completed
python main.py done 1

# Change priority
python main.py prioritize 1 High

# Archive completed tasks
python main.py archive
```

## Requirements

Python 3.8+ (Standard Library with SQLite3).

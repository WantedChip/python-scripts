# Downloads Folder Auto-Organizer

Sorts files in a specified folder (e.g., Downloads) into organized category subfolders based on file extensions, patterns, dates, or custom rules. It can run on-demand or run continuously as a background watcher.

## Usage

### On-Demand Organizing
Scan and sort files in the current directory:
```bash
python downloads_organizer.py
```

Scan and sort files in a specific downloads folder:
```bash
python downloads_organizer.py C:\Users\Username\Downloads
```

### Active Watching (Daemon-like Mode)
Monitor a folder continuously using the `watchdog` library. It detects new downloads as they finish and automatically categorizes them.
```bash
python downloads_organizer.py C:\Users\Username\Downloads --watch
```

### Advanced Options
- `--dry-run`: Preview where files would be moved without actually renaming or moving them.
- `-d`, `--destination <path>`: Move sorted files to a different parent directory rather than organizing them inside the source folder.
- `--conflict {rename,overwrite,skip}`: Choose how to handle duplicate filename collisions in the target folders (default: `rename` by appending `_1`, `_2`, etc.).
- `--date-grouping`: Create a subfolder using modification date (e.g., `Images/2026-07/pic.png`).
- `-c`, `--config <path>`: Load a custom JSON configuration file defining rules and ignored patterns.
- `-v`, `--verbose`: Enable debug logs to troubleshoot file classification or watch events.

## Requirements

If you only use the **on-demand scanning mode**, this script relies purely on the Python standard library (no dependencies).

To use the **active watching mode** (`--watch`), you must install `watchdog`:
```bash
pip install -r requirements.txt
```

## Configuration

You can override default categorization categories and extensions by creating a custom JSON configuration file:

```json
{
  "rules": [
    {
      "name": "Code",
      "extensions": [".py", ".js", ".html", ".css", ".java"]
    },
    {
      "name": "Databases",
      "extensions": [".sql", ".sqlite", ".db"]
    },
    {
      "name": "Invoices",
      "patterns": ["*invoice*", "*bill*"]
    }
  ],
  "default_category": "Others",
  "ignored_patterns": [".*", "desktop.ini"]
}
```

Then run the script pointing to this config:
```bash
python downloads_organizer.py C:\Users\Username\Downloads --config path/to/config.json
```

## Running Tests

To run the unit tests:
```bash
pytest
```

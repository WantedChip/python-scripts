# File Quarantine Cleaner

Identify and safely clean old installer binaries, archive backups, log/temporary cache files, and abandoned downloads.

## Usage

Scan a directory for files older than 30 days:
```bash
python src/file_quarantine_cleaner/main.py /path/to/directory --days 30
```

Scan and move matched files to a quarantine folder:
```bash
python src/file_quarantine_cleaner/main.py /path/to/directory --quarantine-dir /path/to/quarantine
```

Run cleanup automatically without prompting for confirmation:
```bash
python src/file_quarantine_cleaner/main.py /path/to/directory --force
```

Only clean cache and installer files:
```bash
python src/file_quarantine_cleaner/main.py /path/to/directory --category cache --category installer
```

## Options

- `directory`: Optional target folder path to scan (defaults to standard User Downloads folder).
- `--days`: Exclude files modified within this many days (default: `30.0`).
- `--exclude`: Glob patterns to ignore (e.g. `*.pdf`). Can be repeated.
- `--quarantine-dir`: Move identified files to this folder instead of direct deletion.
- `--category`: Filter specific file categories: `installer`, `archive`, `cache`, `abandoned`. Can be repeated.
- `--dry-run`: Reports matching files without making changes to the filesystem.
- `--force`: Delete/quarantine files directly without prompting for confirmation.
- `-v, --verbose`: Enable debug level console logging.

## Quality

Quality: pylint 10.00/10 · 89% coverage · 0 dependencies

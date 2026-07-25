# Backup Rotation Manager

A flexible Python script that manages backup files in a directory according to retention policies (retaining the N most recent backups, or keeping daily and weekly counts) and purging older ones.

## Features

- **Retention Policies**: Retain backups based on count limit, daily retention, or weekly retention.
- **Pattern Matching**: Filter backup files by file pattern or extension (e.g., `*.tar.gz`, `backup_*.db`).
- **Dry-Run Mode**: Preview which backup files would be deleted without making actual filesystem changes.
- **Audit Purge Log**: Log all deleted and retained backups with timestamps and details.

## Usage

```bash
python main.py /path/to/backups --keep 5 --dry-run
python main.py /path/to/backups --pattern "*.tar.gz" --keep-daily 7 --keep-weekly 4
```

## Running Tests

```bash
python -m unittest discover -s tests
```

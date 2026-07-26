# Folder Sync Tool

A high-performance folder synchronization tool supporting one-way and bidirectional synchronization, SHA-256 checksum verification, deletion tracking, and conflict detection.

## Features

- **Sync Directions**:
  - `one-way`: Mirror source directory onto destination.
  - `bidirectional`: Two-way synchronization updating both directories.
- **Checksum Verification**: SHA-256 verification ensures file contents match exactly beyond simple size/mtime checks.
- **Delete Tracking**: Optional deletion of files in destination that no longer exist in source (`--delete`).
- **Conflict Detection**: Detects when files differ in both directories and creates non-destructive conflict copies (`.conflict`).
- **Dry-run Mode**: Preview operations before making filesystem modifications.
- **Sync Log Export**: Saves JSON sync logs detailing every action (copy, update, delete, skip, conflict).

## Usage

```bash
python main.py --source /path/to/src --dest /path/to/dst --direction one-way --delete --checksum --dry-run
```

### Options

- `--source`, `-s`: Source directory path (required).
- `--dest`, `-d`: Destination directory path (required).
- `--direction`: Sync mode (`one-way` or `bidirectional`, default: `one-way`).
- `--delete`: Remove files in destination not present in source (one-way mode).
- `--checksum`: Use SHA-256 hash comparison instead of mtime/size only.
- `--log-file`: Path to write execution log (default: `sync_log.json`).
- `--dry-run`: Preview file operations without altering files.

## Running Tests

```bash
python -m unittest discover tests
```

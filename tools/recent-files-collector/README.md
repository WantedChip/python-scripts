# Recent Files Collector

A Python utility to collect and copy files modified or created within a specified number of days from a source directory tree into a flat destination folder.

## Features

- **Time-based Filtering**: Filter by modification time (`mtime`) or creation time (`ctime`).
- **Extension Filtering**: Limit collection to specific file extensions.
- **Collision Resolution**: Resolve filename collisions in the flat destination using counters or MD5 hash suffixes.
- **Dry-run Mode**: Preview actions without modifying the filesystem.
- **Manifest Generation**: Generates a JSON manifest file listing all collected files, source paths, destination paths, and timestamps.

## Requirements

- Python 3.8+ (Standard library only)

## Usage

```bash
python main.py --source /path/to/source --dest /path/to/destination --days 7 --time-type mtime --extensions .pdf .docx --collision-strategy counter --dry-run
```

### Command Line Arguments

- `--source`, `-s`: Source directory path (required).
- `--dest`, `-d`: Destination directory path (required).
- `--days`, `-n`: Age threshold in days (default: 7).
- `--time-type`: Time attribute to filter by (`mtime` or `ctime`, default: `mtime`).
- `--extensions`, `-e`: Space-separated list of extensions to include (e.g., `.py .md`).
- `--collision-strategy`: Strategy for handling duplicate filenames (`counter` or `hash`, default: `counter`).
- `--manifest`: Path to output JSON manifest file (default: `manifest.json`).
- `--dry-run`: Perform a dry run without copying files.

## Running Tests

```bash
python -m unittest discover tests
```

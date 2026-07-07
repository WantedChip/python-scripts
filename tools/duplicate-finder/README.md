# Duplicate File Finder

Recursively scans directories (or specific files) for duplicate files by content hashing, prints a report of wasted space, and optionally moves duplicate files to a quarantine directory.

## Features

- **Efficient Hashing**: Groups files by size first, then only hashes files of the same size using chunked reading (MD5, SHA-1, or SHA-256) to minimize disk I/O and memory usage.
- **Quarantining**: Safely moves duplicate files to a designated quarantine folder, preserving their relative subfolder structure based on their scan root.
- **Conflict Resolution**: Resolves naming conflicts in the quarantine folder by appending numbered suffixes (e.g. `file_1.txt`) instead of overwriting existing files.
- **Original Selection Strategies**:
  - `shortest-path` (default): Selects the file with the shortest path length (breaking ties alphabetically) as the original.
  - `oldest`: Selects the file with the oldest modification time (`mtime`) as the original.
  - `newest`: Selects the file with the newest modification time (`mtime`) as the original.
- **Smart Path Exclusions**: Excludes patterns like `.git`, `.venv`, and `__pycache__` by default, or accept custom user glob patterns via `--exclude`.
- **Dry-run Option**: Previews files that would be quarantined without actually moving them.
- **Zero Third-Party Dependencies**: Runs on standard Python library.

## Requirements

- Python 3.8+
- No external packages required.

## Usage

### Simple Scan
To scan a directory and see duplicate files and wasted space:
```bash
python duplicate_finder.py /path/to/directory
```

### Scan Multiple Paths
You can pass multiple directories or specific files to scan:
```bash
python duplicate_finder.py /path/to/dir1 /path/to/dir2 /path/to/file.txt
```

### Options

```text
positional arguments:
  paths                 One or more directories (or files) to scan for duplicates.

options:
  -h, --help            show this help message and exit
  -q QUARANTINE, --quarantine QUARANTINE
                        Move duplicate files to this directory instead of deleting or keeping them.
  -d, --dry-run         Show what would be quarantined without actually moving any files.
  --hash {md5,sha1,sha256}
                        Hashing algorithm to use (default: sha256).
  --min-size MIN_SIZE   Minimum file size in bytes to check (default: 0).
  --strategy {shortest-path,oldest,newest}
                        Strategy to pick the 'original' file in a duplicate set (default: shortest-path).
  --exclude EXCLUDE     Shell-style wildcard patterns to exclude from scanning (can be repeated).
  -v, --verbose         Increase logging verbosity.
```

### Examples

#### Scan with Excluded Folders and Custom Hashing
Scan `/data` using MD5 hashing, excluding any files matching `*.log` or paths containing `temp`:
```bash
python duplicate_finder.py /data --hash md5 --exclude "*.log" --exclude "*temp*"
```

#### Quarantine Duplicates with Dry Run (Preview)
Check what duplicate files would be moved to `/tmp/quarantine` from `/my-files`:
```bash
python duplicate_finder.py /my-files --quarantine /tmp/quarantine --dry-run
```

#### Perform Actual Quarantine keeping the Oldest File
Move duplicate files from `/my-files` to `/tmp/quarantine`, making sure the original file kept is the one with the oldest modification time:
```bash
python duplicate_finder.py /my-files --quarantine /tmp/quarantine --strategy oldest
```

## Running Tests

Tests are written using `pytest`. Run tests from the project root:
```bash
pytest tools/duplicate-finder/tests/test_duplicate_finder.py
```

# Duplicate File Finder

A CLI tool to recursively scan directories for duplicate files by comparing file content hashes. It groups files by size first to avoid reading files with unique sizes, and then hashes duplicates to compute wasted space and optionally move them to a quarantine directory.

## Usage

Run the script by passing one or more paths to scan.

```bash
python duplicate_finder.py [paths...]
```

### Examples

**Basic Scan:**
```bash
python duplicate_finder.py /path/to/directory1 /path/to/directory2
```

**Scan and Quarantine Duplicates:**
Moves all duplicate files to `/path/to/quarantine` while preserving their directory structure relative to the scanned folders and resolving filename collisions automatically.
```bash
python duplicate_finder.py /path/to/directory1 --quarantine /path/to/quarantine
```

**Dry Run (Quarantine preview):**
```bash
python duplicate_finder.py /path/to/directory1 --quarantine /path/to/quarantine --dry-run
```

**Other Options:**
- `--hash {md5,sha1,sha256}`: Hashing algorithm (default: `sha256`).
- `--min-size BYTES`: Skip files smaller than this size.
- `-v`, `--verbose`: Enable debug logging.

## Requirements

- Python 3.8+
- Standard Library only (no external dependencies required)

## Testing

To run the unit tests, install `pytest` and execute:
```bash
pytest tests/
```

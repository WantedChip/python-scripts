# Duplicate File Finder CLI

High-performance duplicate file identification and cleanup CLI tool leveraging multi-stage size pre-filtering, partial head hashing, and full SHA-256 chunked content hashing.

## Features

- **Multi-Stage Detection**:
  1. Size grouping (instant skip for unique file sizes).
  2. Partial head hashing (4KB read for fast elimination).
  3. Full chunked SHA-256 hashing (64KB memory-efficient chunks).
- **Flexible Reporting**: Output duplicate reports directly to Console, JSON, or CSV formats.
- **Quarantine Mode**: Safely relocate redundant duplicates to a designated quarantine folder.
- **Delete Mode**: Permanently delete duplicate files while leaving the primary original file intact.
- **Safety Defaults**: Dry-run mode by default; confirmation prompts before destructive actions.

## Usage

```bash
python main.py --dir /path/to/search --json report.json
```

### CLI Options

| Option | Short | Description | Default |
|---|---|---|---|
| `--dir` | `-d` | Target directory to scan | `.` |
| `--min-size` | | Minimum file size in bytes to process | `1` |
| `--exclude` | | Substrings/filenames to ignore | None |
| `--json` | | Path to save JSON report | None |
| `--csv` | | Path to save CSV report | None |
| `--quarantine` | | Move duplicate files to specified directory | None |
| `--delete` | | Permanently delete duplicate files | `False` |
| `--apply` | | Confirm and execute quarantine or deletion | `False` |
| `--yes` | `-y` | Skip confirmation prompt | `False` |

## Examples

### 1. Find and Export Report
```bash
python main.py -d ~/Documents --json duplicates.json --csv duplicates.csv
```

### 2. Move Duplicates to Quarantine
```bash
python main.py -d ~/Downloads --quarantine ~/Downloads/Quarantine --apply
```

### 3. Delete Duplicates
```bash
python main.py -d ~/Pictures --delete --apply --yes
```

## Running Unit Tests

```bash
python -m unittest discover tests
```

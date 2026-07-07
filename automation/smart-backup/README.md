# Smart Backup Script

Performs incremental backups with checksums, exclusion rules, retention policies, post-backup verification, and dry-run mode.

## Features

- **Incremental Backup**: Only copies files that changed since the last run (by modification time or checksum).
- **Checksum Verification**: After backup, verifies every file against its stored hash.
- **Exclusion Rules**: Skip files/directories using glob patterns.
- **Retention Policy**: Automatically delete backup snapshots older than N days.
- **Dry-Run Mode**: Simulate the backup without copying anything.
- **Manifest**: Stores a `.backup_manifest.json` in the destination for incremental state.

## Requirements

No third-party dependencies. Requires Python 3.9+.

## Usage

```bash
# Basic backup
python smart_backup.py --source ~/Documents --dest /mnt/backup/docs

# Checksum-based comparison (more reliable, slower)
python smart_backup.py --source . --dest /backup --mode checksum

# Dry-run preview
python smart_backup.py --source . --dest /backup --dry-run

# Backup with post-run verification
python smart_backup.py --source . --dest /backup --verify

# Exclude files
python smart_backup.py --source . --dest /backup --exclude "*.log" "__pycache__" ".git"

# Apply retention policy (delete backups older than 30 days)
python smart_backup.py --dest /mnt/backup --apply-retention --keep-days 30

# Dry-run retention check
python smart_backup.py --dest /mnt/backup --apply-retention --keep-days 30 --dry-run
```

## Options

| Argument | Description | Default |
|---|---|---|
| `--source DIR` | Source directory to back up | required |
| `--dest DIR` | Backup destination directory | required |
| `--mode` | Comparison: `mtime` or `checksum` | `mtime` |
| `--algo` | Hash algorithm: `md5`, `sha1`, `sha256`, `sha512` | `sha256` |
| `--exclude PATTERN...` | Glob patterns/dirs to skip | `.git __pycache__ *.pyc` |
| `--dry-run` | Simulate without copying | False |
| `--verify` | Verify checksums after backup | False |
| `--apply-retention` | Delete old snapshots from dest | False |
| `--keep-days N` | Days to keep old snapshots | 30 |
| `-v, --verbose` | Verbose logging | False |

## Notes

- The manifest is stored as `.backup_manifest.json` in the destination directory.
- `mtime` mode is fast; `checksum` mode catches bitrot but is slower for large datasets.
- Retention cleanup targets subdirectories named with an ISO 8601 date prefix (`YYYY-MM-DD`).

## Running Tests

```bash
pytest
```

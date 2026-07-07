# Folder Snapshot + Diff Tool

Records a directory's state as a JSON snapshot, then compares two snapshots — or a snapshot against the live directory — to show exactly what was added, removed, or modified.

## Features

- **Snapshot**: Captures file paths, sizes, modification times, and content hashes.
- **Diff**: Compare two snapshot files, or a snapshot against the current live state.
- **Flexible Comparison**: Use checksum-based (reliable) or mtime+size-based (fast) detection.
- **Exclusion Rules**: Skip `.git`, `__pycache__`, and any glob pattern.
- **Multiple Hash Algorithms**: `md5`, `sha1`, `sha256` (default), `sha512`.

## Requirements

No third-party dependencies. Requires Python 3.9+.

## Usage

### Take a Snapshot

```bash
python folder_snapshot.py snapshot --root ./src --output before.json
python folder_snapshot.py snapshot --root ./src --output before.json --label "before-refactor"
python folder_snapshot.py snapshot --root . --output snap.json --no-hash  # fast, mtime-only
```

### Compare Two Snapshots

```bash
python folder_snapshot.py diff --old before.json --new after.json
```

### Compare Snapshot Against Live Directory

```bash
# Check what changed since the snapshot was taken
python folder_snapshot.py diff --old before.json --live
python folder_snapshot.py diff --old before.json --live --no-hash  # mtime-only
python folder_snapshot.py diff --old before.json --live -v  # show unchanged count
```

## Options

### `snapshot`

| Argument | Description | Default |
|---|---|---|
| `--root DIR` | Directory to snapshot | required |
| `--output FILE` | JSON output file path | required |
| `--label TEXT` | Human-readable label | (empty) |
| `--algo` | Hash algorithm: `md5`, `sha1`, `sha256`, `sha512` | `sha256` |
| `--exclude PATTERN...` | Glob patterns to exclude | `.git __pycache__ *.pyc` |
| `--no-hash` | Skip checksum (faster) | False |

### `diff`

| Argument | Description | Default |
|---|---|---|
| `--old FILE` | Reference (older) snapshot | required |
| `--new FILE` | Comparison (newer) snapshot | — |
| `--live` | Compare against current live state | False |
| `--algo` | Hash algorithm for live snapshot | `sha256` |
| `--no-hash` | Use mtime+size comparison only | False |
| `-v, --verbose` | Show unchanged file count | False |

## Notes

- `--new` and `--live` are mutually exclusive; exactly one is required for `diff`.
- Snapshots are portable JSON files — they can be stored alongside a project or in version control.
- `--no-hash` is significantly faster for large directories but will miss content changes if mtime is preserved (e.g., `rsync --times`).

## Running Tests

```bash
pytest
```

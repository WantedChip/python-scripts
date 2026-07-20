# orphan-config

Find settings folders, caches, and application data directories in standard system locations (e.g. AppData or `~/.config`) that were left behind by software that is no longer installed.

## Usage

Scan for orphan configuration candidate directories:

```bash
python orphan_config.py
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Correlation Logic

- **Locations Audited**:
  - **Windows**: `AppData\Roaming`, `AppData\Local`
  - **Unix/macOS**: `~/.config`, `~/Library/Application Support`
- **Active Program Verification**: Checks directory profile names against reachable system executable path lookups (`PATH` variables) and common program installation folders (`C:\Program Files`, `/usr/bin`, `/Applications`).
- **Disk Usage Calculations**: Iterates and aggregates storage size in megabytes occupied by orphaned candidate folders.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

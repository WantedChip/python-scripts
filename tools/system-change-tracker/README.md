# What Changed My System? Tracker

A CLI snapshot utility to track changes made to your local machine (files, environment variables, Python packages, OS programs, active services) before and after running installations or scripts.

## Features

- **File System Snapshotting**: Crawls specified directories and records paths, sizes, mtimes, and SHA-256 hashes recursively.
- **Python Environment Audit**: Queries distributions in the active environment to snapshot installed dependencies.
- **Platform-Aware OS Package Sniffer**:
  - Windows: Crawls `HKLM` and `HKCU` Registry uninstall records to map programs and versions.
  - Linux: Runs `dpkg-query` to catalog dpkg packages.
- **System Services Status Auditing**:
  - Windows: Queries service states using `sc.exe`.
  - Linux: Queries unit states via `systemctl`.
- **Environmental Comparison**:
  - Snapshots environment variables (`os.environ`).
- **Differential System Dashboard**:
  - Compares two snapshot JSON files to output additions, removals, modifications, status transitions, and version jumps in a structured terminal dashboard report.

## Usage

```bash
# Capture a snapshot before installation
python system_change_tracker.py snapshot -o before.json -d c:/Users/Lenovo/Documents

# Perform system installation (npm, pip, msi, apt, etc.)
# ...

# Capture snapshot after installation
python system_change_tracker.py snapshot -o after.json -d c:/Users/Lenovo/Documents

# Diff the snapshots and display visual changelog report
python system_change_tracker.py diff before.json after.json

# Diff the snapshots and write structured difference JSON
python system_change_tracker.py diff before.json after.json -o system_changes.json
```

## Requirements

- Python 3.x (standard library only)

Quality: pylint 10.00/10 · 83% coverage · 0 dependencies

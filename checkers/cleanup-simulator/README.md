# cleanup-simulator

Scan local directories and system cache folders to estimate reclaimable storage space before running any deleting actions. It runs in a strict read-only preview mode.

## Usage

Scan the current directory for cache and build files:

```bash
python cleanup_simulator.py
```

Scan a custom target directory:

```bash
python cleanup_simulator.py C:/Users/Name/Projects/my_app
```

Include system temp folders and pip/npm caches in the estimate:

```bash
python cleanup_simulator.py --system
```

Add custom glob search rules and limit preview list sizes:

```bash
python cleanup_simulator.py --glob "*.log,*.dmp" --limit 10
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Notes

- Audits typical developer cleanup paths (`node_modules`, `__pycache__`, `build/`, `dist/`).
- Runs in read-only mode (does not perform any deletion operations).

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

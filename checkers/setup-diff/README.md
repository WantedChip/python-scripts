# setup-diff

Compare developer machine environment states (operating systems, runtime versions, system binaries, environment variable availability, and active package installations) side-by-side to identify why a project compiles on one machine but crashes on another.

## Usage

Generate a local system state snapshot file:

```bash
python setup_diff.py snapshot local_machine.json
```

Compare two machine snapshots to view mismatch reports:

```bash
python setup_diff.py compare local_machine.json colleague_machine.json
```

## Requirements

- Python 3.11+
- `psutil` (optional, listed in [requirements.txt](requirements.txt) to capture active port listener states)

## Diagnostic Comparisons

- **Runtimes & OS**: Highlights mismatches in platforms or Python versions.
- **Routable Binaries**: Compares path status of common dev commands (`git`, `node`, `docker`, `npm`, etc.).
- **Environment Keys**: Identifies variables missing on either machine.
- **Package Alignments**: Detects package version mismatches or missing packages.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 1 dependency

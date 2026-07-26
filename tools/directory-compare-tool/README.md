# Directory Compare Tool

Recursively compare two directory trees (`Dir A` vs `Dir B`) and report missing files, extra files, and modified files by size, modification timestamp, and SHA-256 hash.

## Features
- Recursive directory scanning and comparison.
- Path filtering via `--include` and `--exclude` glob patterns.
- SHA-256 binary hash verification for detecting modified files.
- Formatted CLI side-by-side comparison summary.
- Export results to structured JSON files (`--json-output`).

## Usage

### Compare Two Directories
```bash
python main.py /path/to/dir_a /path/to/dir_b
```

### Exclude Files & Export JSON Report
```bash
python main.py /path/to/dir_a /path/to/dir_b --exclude "*.tmp" --exclude ".git/*" --json-output report.json
```

### Quick Compare (Disable Hash Check)
```bash
python main.py /path/to/dir_a /path/to/dir_b --no-hash
```

## Running Tests
```bash
python -m unittest discover -s tests
```

# Large File Finder

Scan directory trees to detect files exceeding size thresholds, generate extension breakdowns, and export top N reports in Console, JSON, or CSV formats.

## Features

- **Recursive Scanning**: Scans directory trees recursively to find files exceeding configurable thresholds.
- **Human-Readable Size Parsing**: Accepts threshold values such as `100MB`, `1.5GB`, `500KB`, or raw bytes.
- **Top N Reports**: Easily isolate the top N largest files across your disk/directory.
- **Extension & Type Breakdown**: Computes disk space distribution grouped by file extensions.
- **Multiple Export Formats**: Supports `console`, `json`, and `csv` outputs.

## Usage

```bash
python main.py --path /path/to/scan --min-size 100MB --top 20 --format console --output report.json
```

### Options

- `--path`, `-p`: Directory path to scan (required).
- `--min-size`, `-s`: Minimum file size threshold (e.g., `100MB`, `1GB`, `500KB`, default: `100MB`).
- `--top`, `-n`: Limit report to top N largest files.
- `--format`, `-f`: Output format (`console`, `json`, `csv`, default: `console`).
- `--output`, `-o`: File path to save output report.

## Running Tests

```bash
python -m unittest discover tests
```

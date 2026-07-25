# Time Sync Auditor

A multi-host audit tool for checking NTP and chrony synchronization health across Linux hosts or parsing collected time sync logs and JSON outputs.

## Features

- **Multi-Service Log Parsing**: Parses raw CLI outputs from `chronyc tracking`, `chronyc sources`, `ntpstat`, and `ntpq -p`.
- **JSON Batch Processing**: Ingests multi-host aggregated JSON files containing outputs from remote node monitoring agents.
- **Health Threshold Evaluation**:
  - Offset drift thresholds (configurable warning & critical limits in milliseconds).
  - Stratum limit checks (flags high stratum sources or unsynchronized nodes).
  - Frequency drift checks (ppm).
- **Aggregated Reporting**: Summarizes total audited hosts, healthy/warning/critical node metrics, and identifies degraded machines.
- **Multiple Export Formats**: Formatted terminal tables, machine-readable JSON, and CSV exports.

## Usage

```bash
# Audit a single chrony tracking output log file
python main.py --file chrony_tracking.log --host node-01

# Ingest multi-host JSON dataset and set strict offset thresholds
python main.py --json-input cluster_time_status.json --max-offset-warn 5.0 --max-offset-crit 50.0

# Export results to CSV
python main.py --json-input nodes.json --format csv --output time_sync_audit.csv
```

## Options

- `-f`, `--file`: Path to time sync output file (`chronyc tracking`, `ntpstat`, etc.).
- `-j`, `--json-input`: Path to JSON file containing multi-host status outputs.
- `-H`, `--host`: Hostname label for single file input mode (default: `localhost`).
- `-o`, `--output`: Path to write report file (defaults to stdout).
- `--format`: Output format (`table`, `json`, or `csv`).
- `--max-offset-warn`: Offset warning threshold in milliseconds (default: 10.0 ms).
- `--max-offset-crit`: Offset critical threshold in milliseconds (default: 100.0 ms).
- `--max-stratum-warn`: Stratum warning threshold (default: 4).
- `--max-drift-ppm`: Frequency drift warning threshold in ppm (default: 100.0 ppm).

## Testing

```bash
python -m unittest discover tests
```

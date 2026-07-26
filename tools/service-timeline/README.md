# Service Timeline

`service-timeline` merges logs, container events, deployments, and process events from multiple sources into a single chronological timeline for incident investigation.

## Features

- **Multi-Format Timestamp Parser**: Automatically recognizes ISO8601, Syslog format, and Epoch timestamps.
- **Interleaved Incident Timeline**: Merges disparate log files into a unified time series.
- **Filtering & Filtering Options**: Filter timeline by minimum severity (`WARN`, `ERROR`, `CRITICAL`), keyword, or time window.
- **Formatted CLI & JSON Output**: Supports interactive terminal view or structured JSON output.

## Usage

```bash
# Merge multiple service log files
python main.py app.log container.log syslog.log

# Filter by minimum severity ERROR with JSON output
python main.py app.log nginx.log --min-severity ERROR --json

# Filter by specific keyword
python main.py app.log --keyword "out of memory"
```

## Running Tests

```bash
python -m unittest discover -s tests
```

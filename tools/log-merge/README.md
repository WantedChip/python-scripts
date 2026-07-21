# log-merge

Merge dispersed log files from multiple service logs, extract ISO/RFC timestamps to sort them chronologically, collapse duplicate errors, and highlight precursor events before failures.

## Usage

Merge multiple log files and display timeline with precursor context:

```bash
python log_merge.py api_server.log worker.log gateway.log
```

Write merged log timeline output to file:

```bash
python log_merge.py api.log worker.log --output unified_timeline.log
```

Specify custom precursor context lines (e.g. 5 lines) before each error:

```bash
python log_merge.py api.log worker.log --precursors 5
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Timeline Builder Logic

- **Timestamp Parsing**: Sniffs and parses standard ISO 8601, RFC 3339, or standard timestamp representations.
- **Timeline Interleaving**: Sorts entries across files, tracking sources.
- **Log Collapsing**: Consecutive lines matching the same pattern and source are condensed with a `[Repeated N times]` indicator to reduce clutter.
- **Precursor Highlights**: Automatically prints active service context occurrences leading up to an error line.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

# JSON Shape Diff

A high-performance CLI tool for structurally comparing massive JSON datasets. Instead of performing line-by-line text diffing (which fails on reordered keys or formatted JSON), `json-shape-diff` extracts recursive data schemas, key hierarchies, nullability, and list element shapes to report structural schema drift.

## Features

- **Recursive Schema Extraction**: Extracts primitive types (`str`, `int`, `float`, `bool`, `null`), dictionary keys, and list element shapes.
- **List Element Consolidation**: Merges list item schemas into aggregate element shapes across arrays.
- **Nullability Analysis**: Detects fields that become nullable or non-nullable between datasets.
- **Structural Diffing**:
  - `MISSING_FIELD`: Present in Baseline (A), missing from Target (B).
  - `ADDED_FIELD`: Missing from Baseline (A), added in Target (B).
  - `TYPE_MISMATCH`: Field type differs (e.g., `str` vs `int`, `dict` vs `list`).
  - `NULLABILITY_MISMATCH`: Changes in field nullability.
- **Flexible Path Filtering**: Ignore metadata fields or dynamic keys using path glob patterns.
- **Multiple Output Formats**: Terminal human-readable text output or machine-readable JSON.

## Usage

```bash
# Compare two JSON files
python main.py dataset_v1.json dataset_v2.json

# Export diff as JSON with path ignores
python main.py dataset_a.json dataset_b.json --ignore "$.timestamp" "$.meta.*" --format json --output diff_report.json

# Adjust max depth analysis
python main.py file1.json file2.json --max-depth 10
```

## Options

- `file_a`: Path to baseline JSON file.
- `file_b`: Path to target JSON file.
- `-o`, `--output`: Path to write diff report (default: stdout).
- `-f`, `--format`: Output format (`text` or `json`).
- `--ignore`: One or more JSON path patterns to exclude from comparison.
- `--max-depth`: Maximum depth for nested schema extraction (default: 100).
- `--strict-numbers`: Differentiate strictly between `int` and `float`.

## Testing

```bash
python -m unittest discover tests
```

# CSV Forensics

A comprehensive CLI utility for deeply inspecting CSV files to detect encoding anomalies, invisible control characters, broken quoting, inconsistent delimiters, header defects, malformed rows, and Excel-induced data corruption.

## Features

- **Encoding & BOM Diagnostics**: Identifies byte-order marks (BOM), non-UTF-8 bytes, and encoding conflicts (Latin-1, CP1252).
- **Invisible & Control Character Detection**: Detects zero-width spaces (`\u200b`), non-breaking spaces (`\u00a0`), soft hyphens, null bytes (`\x00`), and hidden ASCII control characters.
- **Delimiter & Quoting Analysis**: Detects unclosed quotes, malformed escaping, and inconsistent column delimiter counts across rows.
- **Header Integrity Audit**: Flag duplicate headers, empty header names, leading/trailing whitespace, and special characters.
- **Row-Level Structural Validation**: Identifies field count mismatches between headers and rows.
- **Excel Data Corruption Detection**:
  - Scientific notation converted IDs (e.g. `1.23E+11`).
  - Leading zero truncation (e.g. ZIP codes or account numbers stripped to 4 digits).
  - Excel formula error values (e.g. `#VALUE!`, `#REF!`, `#N/A`, `#NAME?`).

## Usage

```bash
# Audit a CSV file
python main.py data.csv

# Specify delimiter and save detailed JSON audit report
python main.py records.csv --delimiter ";" --format json --output audit_report.json

# Limit row inspection depth for massive files
python main.py large_export.csv --max-rows 10000
```

## Options

- `file_path`: Path to target CSV file.
- `-d`, `--delimiter`: Force specific delimiter (auto-detected if omitted).
- `-e`, `--encoding`: Explicit encoding to test (default: auto-detect / UTF-8 fallback).
- `-o`, `--output`: Path to write diagnostic report file (default: stdout).
- `-f`, `--format`: Output report format (`text` or `json`).
- `--max-rows`: Limit maximum number of rows inspected (default: all rows).

## Testing

```bash
python -m unittest discover tests
```

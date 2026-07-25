# JSON to CSV Converter

A Python utility to convert JSON array documents or JSON Lines (`.jsonl`) files into CSV format.

## Features

- **Format Autodetection**: Parses standard JSON arrays, single JSON objects, or line-delimited JSON (`.jsonl`).
- **Nested Object Flattening**: Converts nested objects (e.g. `{"user": {"name": "Alice"}}`) into dot-notated columns (`user.name`).
- **Union Header Detection**: Dynamically creates header columns representing the union of all keys across all records.
- **Custom Delimiters**: Supports standard CSV comma delimiters or TSV / custom delimiters.

## Usage

```bash
# Convert a standard JSON array file to CSV
python main.py data.json output.csv

# Convert a JSONL file to CSV
python main.py logs.jsonl output.csv --jsonl

# Customize nested key separator and CSV delimiter
python main.py input.json output.tsv --sep "_" --delimiter "\t"

# Disable flattening of nested JSON structures
python main.py input.json output.csv --no-flatten
```

## Running Tests

```bash
python -m unittest discover -s tests
```

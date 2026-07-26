# JSON Formatter CLI

A powerful command-line utility to pretty-print, minify, query (jq-style path queries), and validate JSON schemas.

## Features
- **Pretty Printing**: Formats raw JSON string/file input with custom indent levels and syntax highlighting colors.
- **Minification**: Compresses JSON output into a single compact line.
- **Path Querying**: Query JSON structures using dot-separated key and array indexing paths (e.g. `users[0].name` or `store.books.1.title`).
- **Schema Validation**: Validates JSON content structure against required keys and data types from a JSON schema definition.

## Usage

```bash
# Pretty-print JSON file with ANSI color highlighting
python main.py format sample.json

# Format without colors
python main.py format sample.json --no-color

# Query nested JSON value (jq-style path)
python main.py query sample.json "users[0].name"

# Minify JSON file
python main.py minify sample.json

# Validate JSON file against schema definition
python main.py validate sample.json schema.json
```

## Running Tests

```bash
python -m unittest discover -s tests
```

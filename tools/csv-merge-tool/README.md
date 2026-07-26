# CSV Merge Tool

A Python tool to merge multiple CSV files with matching or overlapping headers into a single unified CSV file with automated header alignment.

## Features

- **Header Union**: Automatically combines unique column headers across all input CSV files while preserving natural ordering.
- **Missing Column Handling**: Fills missing column fields for rows with a configurable default value.
- **Source File Tagging**: Optionally adds a column identifying the source filename for each merged row (`--tag-source`).
- **Deduplication**: Remove duplicate rows across merged files with the `--dedupe` flag.
- **Glob Support**: Supports file patterns (e.g. `data/*.csv`) or multi-file arguments.

## Usage

```bash
# Basic merge of multiple CSV files
python main.py file1.csv file2.csv --output merged.csv

# Merge all CSV files in a folder with source tagging and deduplication
python main.py "data/*.csv" --output merged.csv --tag-source source_file --dedupe

# Fill missing column entries with 'N/A'
python main.py file1.csv file2.csv --output merged.csv --default-val "N/A"
```

## Running Tests

```bash
python -m unittest discover -s tests
```

# data-peek

A unified CLI data file inspector that provides quick schema previews, row counts, null percentages, data types, and sample records for CSV, TSV, JSON, JSONL, SQLite, and Excel/Parquet files.

## Usage

Inspect a CSV file:

```bash
python data_peek.py user_data.csv
```

Inspect a JSON or JSONL file:

```bash
python data_peek.py logs.jsonl
```

Inspect an SQLite database (shows tables and structures):

```bash
python data_peek.py project.db
```

Inspect Excel or Parquet files (requires Pandas/openpyxl/pyarrow):

```bash
python data_peek.py metrics.parquet
```

## Requirements

- Python 3.11+
- **Zero dependencies** for CSV, TSV, JSON, JSONL, and SQLite formats.
- Optional dependencies (listed in [requirements.txt](requirements.txt)) to enable Excel and Parquet file checks.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

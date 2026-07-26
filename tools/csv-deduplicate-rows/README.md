# CSV Deduplicate Rows Tool

A CLI tool to remove duplicate rows from CSV files based on one or more specified key columns. Supports keeping first or last occurrence, case-insensitive comparison, and fuzzy string similarity deduplication.

## Features

- **Multi-Column Keys**: Group and match duplicates by single or multiple header names.
- **Retention Strategies**: Retain `first` or `last` occurrence of duplicated records.
- **Case-Insensitive Mode**: Toggle case-insensitivity during matching.
- **Fuzzy String Matching**: Detect approximate duplicates using string similarity ratios (0.0 - 1.0).
- **Deduplication Metrics**: Reports total input rows, retained rows, and removed row counts.

## Usage

### Basic Deduplication (Exact Key Match)
```bash
python main.py --input customers.csv --keys "email,phone" --output deduplicated.csv
```

### Case-Insensitive Deduplication (Retain Last)
```bash
python main.py --input users.csv --keys "email" --keep last --ignore-case --output clean_users.csv
```

### Fuzzy String Deduplication
```bash
python main.py --input contacts.csv --keys "company_name" --fuzzy-threshold 0.85 --output deduplicated_contacts.csv
```

### Run Unit Tests
```bash
python -m unittest discover -s tests
```

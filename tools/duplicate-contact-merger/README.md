# Duplicate Contact Merger

Merges duplicate contact records from CSV files using fuzzy name matching (`difflib.SequenceMatcher`) and exact normalized match keys on email address and phone numbers. Field conflicts across merged records are resolved using rule-based strategies.

## Features

- **Fuzzy Name Matching**: Calculates string similarity using `difflib.SequenceMatcher` to group variation names (e.g. `John Smith` vs `John A. Smith`).
- **Exact Match Keys**: Standardizes email (lowercased) and phone numbers (digits extracted) for exact key matching.
- **Cluster Merging**: Connects duplicate records into disjoint clusters and resolves conflicts field-by-field.
- **Conflict Resolution Strategies**: Supports `prefer_longest` (chooses most complete string) or `prefer_non_null`.
- **Merge Audit Log**: Exports JSON audit log details showing merged record clusters.

## Usage

```bash
python main.py -i contacts.csv -o clean_contacts.csv --name-col "Full Name" --email-col "Email" --phone-col "Phone" --threshold 0.85 --log-file merge_report.json
```

### Command Line Options

- `-i, --input-file`: (Required) Path to input CSV file.
- `-o, --output-file`: (Required) Path to output merged CSV file.
- `--name-col`: CSV header name for contact name column.
- `--email-col`: CSV header name for email column.
- `--phone-col`: CSV header name for phone number column.
- `--threshold`: Fuzzy similarity score threshold (0.0 to 1.0). Default: `0.85`.
- `--strategy`: Merge conflict resolution strategy (`prefer_longest`, `prefer_non_null`). Default: `prefer_longest`.
- `--log-file`: Optional JSON file path to export detailed cluster merge log.

## Running Unit Tests

```bash
python -m unittest discover -s tests
```

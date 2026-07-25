# Email Validator & Cleaner

Validates and cleans email address lists in CSV files. Performs syntax validation, disposable domain detection, optional DNS/MX record verification, deduplication, and exports clean/flagged CSV reports.

## Features

- **Syntax Validation**: Ensures email strings conform to RFC 5322 specifications.
- **Disposable Domain Detection**: Checks against a built-in library of disposable email domain providers (`mailinator.com`, `tempmail.com`, etc.) with support for custom domain lists.
- **DNS / MX Check**: Optional socket-based DNS resolution to check if the domain host exists.
- **Deduplication**: Identifies and flags duplicate emails in the list.
- **Flexible Output**: Generates clean output CSV and optional flagged CSV file for invalid entries.

## Usage

```bash
python main.py -i input_emails.csv -o clean_emails.csv -c "Email" --check-mx --output-flagged invalid_emails.csv
```

### Command Line Options

- `-i, --input-file`: (Required) Path to input CSV file.
- `-o, --output-file`: (Required) Path to main output CSV file.
- `-c, --column`: (Required) Header name or 0-indexed position of email column.
- `--check-mx`: Perform DNS lookup verification on email domain.
- `--disposable-file`: Path to custom text file with disposable domain names.
- `--no-dedupe`: Disable deduplication checking.
- `--output-flagged`: Optional path to output CSV containing invalid/flagged rows only.

## Running Unit Tests

```bash
python -m unittest discover -s tests
```

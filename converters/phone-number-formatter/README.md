# Phone Number Formatter

Standardizes phone numbers in CSV columns into standard E.164 international format (`+14155552671`) or custom display formats (`national`, `international`, `digits_only`). Validates input numbers and tags each row as `VALID`, `INVALID`, or `EMPTY`.

## Features

- **E.164 Formatting**: Prepends country codes and standardizes digit strings according to ITU-T E.164 specifications.
- **Multiple Output Formats**: Supports `e164`, `international`, `national`, and `digits_only`.
- **Extension Extraction**: Recognizes extensions (`ext 123`, `x45`, `#101`) and preserves them in output formatted values.
- **Country Code Resolution**: Maps country ISO codes (`US`, `UK`, `IN`, `DE`, `FR`, etc.) or numerical call codes to default un-prefixed numbers.
- **CSV Integration**: Appends standardized values and validation tags as new columns in output CSV files.

## Usage

```bash
python main.py -i contacts.csv -o formatted_contacts.csv -c "phone_number" --default-country US --format e164
```

### Command Line Options

- `-i, --input-file`: (Required) Path to input CSV file.
- `-o, --output-file`: (Required) Path to output CSV file.
- `-c, --column`: (Required) Target phone column header name or 0-indexed column position.
- `--default-country`: Default country code or ISO (e.g. `US`, `UK`, `+1`, `44`). Default: `US`.
- `--format`: Target format mode (`e164`, `international`, `national`, `digits_only`). Default: `e164`.
- `--output-column`: Header name for formatted phone numbers. Default: `formatted_phone`.
- `--status-column`: Header name for validation status. Default: `phone_status`.

## Running Unit Tests

```bash
python -m unittest discover -s tests
```

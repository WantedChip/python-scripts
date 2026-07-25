# Currency Normalizer

Converts mixed currency strings (e.g. `$1,234.50`, `€1.234,50`, `¥5000`, `1234.5 USD`, `(£500.25)`, `-$50.00`) in CSV columns into standardized decimal float numbers and ISO 4217 currency codes.

## Features

- **Symbol & ISO Code Extraction**: Resolves symbols (`$`, `€`, `£`, `¥`, `₹`, `C$`, `A$`, etc.) and ISO currency codes (`USD`, `EUR`, `GBP`, `JPY`, `INR`, etc.).
- **Automatic Separator Detection**: Handles US/UK dot-decimal (`1,234.50`), European comma-decimal (`1.234,50`), and space-separated thousands (`1 234,50`).
- **Negative Amount Support**: Normalizes parenthesized negative amounts `(£500.25)` and minus-prefixed amounts `-$50.00`.
- **CSV Integration**: Adds `normalized_amount`, `currency_code`, and `normalization_status` columns to output CSV.

## Usage

```bash
python main.py -i transactions.csv -o normalized_transactions.csv -c "amount" --default-currency USD
```

### Command Line Options

- `-i, --input-file`: (Required) Path to input CSV file.
- `-o, --output-file`: (Required) Path to output CSV file.
- `-c, --column`: (Required) Target currency column header name or 0-indexed column position.
- `--default-currency`: Fallback ISO 4217 currency code if symbol/code is missing. Default: `USD`.

## Running Unit Tests

```bash
python -m unittest discover -s tests
```

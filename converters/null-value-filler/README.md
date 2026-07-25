# CSV Null Value Filler

A Python utility to detect and fill missing, null, or empty values in CSV files using various strategies.

## Features

- Detects standard missing value representations (`""`, `N/A`, `null`, `None`, `NA`, `NaN`, etc.) or custom missing tokens.
- Supports multiple fill strategies:
  - `constant`: Fill with a specified static value.
  - `mean`: Fill numeric columns with the column mean.
  - `median`: Fill numeric columns with the column median.
  - `mode`: Fill columns with the most frequent value.
  - `ffill`: Forward fill (propagate last valid value).
  - `bfill`: Backward fill (propagate next valid value).
- Target specific columns or apply globally across all columns.

## Usage

```bash
# Fill missing values with constant 'N/A'
python main.py input.csv output.csv --strategy constant --value "N/A"

# Fill missing values in specific columns with column mean
python main.py input.csv output.csv --strategy mean --columns age salary

# Forward-fill missing values
python main.py input.csv output.csv --strategy ffill
```

## Running Tests

```bash
python -m unittest discover -s tests
```

# CSV Outlier Detector

Flags statistical outliers in numeric CSV columns using Interquartile Range (IQR) or Z-Score detection methods.

## Features

- Supports **IQR** and **Z-score** statistical algorithms.
- Custom threshold configuration.
- Automatically processes all numeric columns or specific target columns.
- Outputs summary stats and flagged outlier records.
- JSON and CSV output report export options.

## Usage

```bash
python main.py data.csv -m iqr -t 1.5 -o report.json
python main.py data.csv -c salary age -m zscore -t 3.0
```

## Arguments

- `input_csv`: Path to input CSV file.
- `-c, --column`: Column name(s) to process (optional).
- `-m, --method`: Outlier detection method (`iqr` or `zscore`, default: `iqr`).
- `-t, --threshold`: Custom threshold (default: 1.5 for IQR, 3.0 for Z-score).
- `-o, --output`: Optional output path (`.json` or `.csv`).

## Requirements

Python 3.8+ (Standard Library only).

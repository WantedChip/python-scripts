# Whitespace Cleaner

A Python utility to trim leading, trailing, and excessive internal whitespace from text files, CSV, or TSV documents.

## Features

- **CSV/TSV Cell Cleaning**: Trims leading/trailing whitespace and collapses multiple internal spaces per cell.
- **Line & Text Cleaning**: Normalizes line endings (`\r\n` -> `\n`) and cleans plain text lines.
- **Tab-to-Space Conversion**: Converts tab characters (`\t`) to a configurable number of spaces (`--convert-tabs`, `--tab-width`).
- **In-Place Output**: Option to overwrite the original file directly with `--in-place`.

## Usage

```bash
# Clean CSV file to a new file
python main.py data.csv cleaned_data.csv

# Clean text file in-place, converting tabs to 2 spaces
python main.py document.txt --in-place --convert-tabs --tab-width 2

# Clean TSV file without collapsing internal spaces
python main.py records.tsv clean_records.tsv --mode tsv --no-collapse
```

## Running Tests

```bash
python -m unittest discover -s tests
```

# Find and Replace Text

A command-line tool for performing recursive search and replace operations across text files in a directory tree, featuring regular expression support, file extension filters, diff previews, and replacement metrics summary.

## Features

- **Regex & Literal Search**: Use simple literal search or powerful regular expressions.
- **Dry-Run Diff Preview**: Preview changes using standard unified diff output (`difflib`) before writing to disk.
- **Extension Filtering**: Restrict search to specific file extensions (e.g., `--ext .py .md .txt`).
- **Detailed Metrics**: Summarizes total scanned files, modified files, and replacement counts.

## Usage

```bash
# Preview replacing "foo" with "bar" in python files (dry-run)
python main.py /path/to/project --search "foo" --replace "bar" --ext .py --dry-run

# Execute regex replacement across all files
python main.py /path/to/project --search "v1\.(\d+)" --replace "v2.\1" --regex
```

## Running Tests

```bash
python -m unittest discover -s tests
```

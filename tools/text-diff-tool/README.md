# Text Diff Tool

A Python CLI tool to compare two text files line-by-line, generating unified or side-by-side diff reports with summary metrics (additions, deletions, modifications, unchanged lines).

## Features
- Unified and Side-by-Side diff formats
- Line-by-line comparison with line numbers
- Summary statistics of line changes
- Optional ANSI colorized output for terminal viewing
- Standard library implementation (`difflib`)

## Usage

```bash
# Unified diff
python main.py file1.txt file2.txt --format unified

# Side-by-side diff with color
python main.py file1.txt file2.txt --format side-by-side --color
```

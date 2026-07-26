# ASCII Table Generator CLI

A command-line tool written in Python to convert CSV or TSV data into beautifully formatted ASCII tables for terminal display.

## Features
- **Multiple Border Styles**: `grid`, `simple`, `markdown`, `fancy`
- **Text Alignment**: `left`, `right`, `center`
- **Input Flexibility**: Accepts file paths or standard input (stdin)
- **Auto Delimiter Detection**: Supports CSV and TSV seamlessly

## Usage

```bash
# From file with grid style
python main.py -i data.csv -s grid

# From stdin with markdown style and right alignment
cat data.tsv | python main.py -s markdown -a right
```

## Running Tests

```bash
python -m unittest discover -s tests
```

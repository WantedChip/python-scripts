# Text Case Converter

A command-line tool for converting text strings or files between various letter casings:
`lowercase`, `uppercase`, `titlecase`, `camelcase`, `snakecase`, `sentencecase`, and `kebabcase`.

## Features

- **Multiple Case Modes**: Supports `lower`, `upper`, `title`, `camel`, `snake`, `sentence`, and `kebab`.
- **In-Place File Conversion**: Optionally modify input files in-place or write converted output to stdout / new file.
- **Stdin Stream Support**: Pipe text directly via standard input.

## Usage

```bash
# Convert file to camelCase and print to stdout
python main.py sample.txt --mode camel

# Convert file in-place to snake_case
python main.py sample.txt --mode snake --in-place

# Pipe text into stdin
echo "hello world test" | python main.py --mode title
```

## Running Tests

```bash
python -m unittest discover -s tests
```

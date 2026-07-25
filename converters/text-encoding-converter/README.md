# Text Encoding Converter

A Python utility to detect text file encodings (ASCII, UTF-8, UTF-16, Windows-1252, Latin-1, etc.) via BOM and byte sequence inspection, and convert text files cleanly into target encodings.

## Features

- Detects BOM markers (UTF-8, UTF-16LE, UTF-16BE, UTF-32LE, UTF-32BE).
- Byte sequence heuristics for ASCII, UTF-8, Windows-1252, and Latin-1 detection.
- Error handling modes: `strict`, `ignore`, `replace`.
- Supports single-file and directory bulk conversion modes.

## Usage

### Single File Conversion
```bash
# Auto-detect source encoding and convert to UTF-8
python main.py input.txt output.txt --target utf-8

# Convert Windows-1252 to UTF-8 with custom error handling
python main.py input.txt output.txt --source windows-1252 --target utf-8 --errors ignore
```

### Bulk Directory Conversion
```bash
# Convert all .txt files in a directory to UTF-8
python main.py input_folder/ output_folder/ --bulk --pattern "*.txt" --target utf-8
```

## Running Tests

```bash
python -m unittest discover -s tests
```

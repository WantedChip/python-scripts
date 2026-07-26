# Smart File Classifier Tool

Classify files independent of their extensions by inspecting binary header magic numbers, optionally correct mislabeled file extensions, and organize files into type-based category subfolders.

## Features
- Binary header magic signature classification (`images`, `documents`, `archives`, `executables`, `audio`).
- Extension correction flag (`--fix-extensions`) to align mislabeled extensions with magic bytes.
- Flexible operations: `copy` or `move` files into category destination subfolders.
- `--dry-run` safety mode to inspect actions beforehand.
- Structured JSON classification logging (`--log-file`).

## Usage

### Classify Directory Files (Copy Mode)
```bash
python main.py /path/to/unsorted /path/to/sorted_output
```

### Move Files & Fix Mislabeled Extensions
```bash
python main.py /path/to/unsorted /path/to/sorted_output --mode move --fix-extensions
```

### Dry Run with Log Export
```bash
python main.py /path/to/unsorted /path/to/sorted_output --dry-run --log-file classification.json
```

## Running Tests
```bash
python -m unittest discover -s tests
```

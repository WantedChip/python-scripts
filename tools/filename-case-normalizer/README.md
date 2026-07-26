# Filename Case Normalizer

A bulk filename case normalizer CLI supporting multiple casing modes, collision handling, dry-run preview, and undo manifests.

## Features

- Casing Modes: `lowercase`, `uppercase`, `title`, `snake`.
- Collision Prevention: `append_number`, `skip`, `overwrite`.
- Dry-run preview mode `--dry-run`.
- JSON manifest creation (`--manifest`) and restoration (`--undo`).

## Usage

```bash
# Normalize filenames in a directory to snake_case
python main.py /path/to/folder --mode snake

# Preview changes without modifying files
python main.py /path/to/folder --mode lowercase --dry-run

# Save undo manifest
python main.py /path/to/folder --mode title --manifest undo.json

# Undo renames using manifest
python main.py --undo undo.json
```

## Requirements

Python 3.8+ (Standard Library only).

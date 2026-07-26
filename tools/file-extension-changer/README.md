# File Extension Changer Tool

Safely change file extensions in bulk while validating file header magic bytes to prevent mislabeling files.

## Features
- Header content validation using binary magic signatures (PNG, JPEG, PDF, ZIP, EXE, etc.).
- Mismatch detection warning when proposed extension does not match binary magic number.
- Batch directory processing with glob filtering.
- `--dry-run` mode to preview rename operations safely.
- `--force` flag to bypass header validation warnings.

## Usage

### Single File Rename
```bash
python main.py /path/to/image.tmp -e .png
```

### Dry-run Batch Rename
```bash
python main.py /path/to/folder -e .jpg --pattern "*.dat" --dry-run
```

### Force Rename on Mismatch
```bash
python main.py /path/to/document.bin -e .pdf --force
```

## Running Tests
```bash
python -m unittest discover -s tests
```

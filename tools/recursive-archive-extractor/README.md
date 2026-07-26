# Recursive Archive Extractor Tool

Recursively extract nested archives (`.zip`, `.tar`, `.tar.gz`, `.tar.bz2`) with password list retry support and resource protection controls against zip bomb security risks.

## Features
- Recursive nested archive extraction up to configurable `--max-depth`.
- Password list retry support for encrypted ZIP archives (`--password`, `--passwords-file`).
- Anti-archive bomb safeguards:
  - Max extraction depth limit (`--max-depth`).
  - Max total size limit in MB (`--max-size-mb`).
  - Max extracted file count limit (`--max-files`).
  - Zip Slip / path traversal attempt detection and rejection.
- Summary extraction report detailing files extracted, byte volume, and errors.

## Usage

### Basic Archive Extraction
```bash
python main.py /path/to/archive.zip /path/to/extracted_output
```

### Encrypted Archive with Password List
```bash
python main.py /path/to/archive.zip /path/to/output --password secret123 --passwords-file /path/to/wordlist.txt
```

### Restricted Security Limits
```bash
python main.py /path/to/nested.tar.gz /path/to/output --max-depth 3 --max-size-mb 500 --max-files 2000
```

## Running Tests
```bash
python -m unittest discover -s tests
```

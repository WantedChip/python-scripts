# Folder Permission Reporter Tool

Audit file and folder permissions across Unix and Windows systems. Detect overly permissive bit configurations (world-writable paths, executable data files, missing sticky bits) and provide recommended remediation commands.

## Features
- Stat mode inspection evaluating Unix file permission bits (`st_mode`).
- Risk classification levels:
  - `HIGH`: World-writable files/folders, SUID/SGID executable binaries.
  - `MEDIUM`: Executable data files (`.txt`, `.json`, `.csv`, `.xml`, etc.), group-writable files.
  - `LOW`: Minor permission irregularities.
- Tailored shell command recommendations (e.g. `chmod 644`, `chmod +t`, `chmod o-w`).
- Formatted CLI table output and JSON export (`--json-output`).

## Usage

### Basic Audit
```bash
python main.py /path/to/audit_folder
```

### Minimum Risk Level Filter & JSON Export
```bash
python main.py /path/to/audit_folder --min-risk HIGH --json-output audit_report.json
```

## Running Tests
```bash
python -m unittest discover -s tests
```

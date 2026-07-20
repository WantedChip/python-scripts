# docs-drift

Scan documentation directory markdown files and trace referenced file paths, settings configuration keys, and API function names against active codebase files to highlight broken mappings or out-of-date setup descriptions.

## Usage

Scan documentation drifts in the current directory:

```bash
python docs_drift.py
```

Specify custom source and documentation directories:

```bash
python docs_drift.py --src C:/Users/Name/Projects/my_app/src --docs C:/Users/Name/Projects/my_app/docs
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Diagnostics Performed

- **Path Checks**: Extracts Markdown link destination paths and verifies if targets exist on the local disk.
- **Code Reference Audits**: Scans inline code blocks (e.g. `CONFIG_KEY` or `run_setup()`), and checks if the string exists anywhere inside active source code or configuration files.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

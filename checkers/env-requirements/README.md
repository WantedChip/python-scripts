# env-requirements

Scan source code, Docker configs, and setup documentation to compile a consolidated report of active, required, undocumented, and stale environment variables.

## Usage

Scan environment variables configurations in the current directory:

```bash
python env_requirements.py
```

Scan a custom target directory:

```bash
python env_requirements.py C:/Users/Name/Projects/my_app
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Heuristics Scanned

- **Source Code checks**: Scans Python files recursively, checking for `os.environ[...]` (required variables) and `os.getenv(...)` (optional variables) references.
- **Declarations mapping**: Scans `.env.example` configurations and `docker-compose.yml` keys.
- **Correlation analysis**: Flags variables referenced in source but missing from `.env.example` (Undocumented) and variables in `.env.example` never referenced in source (Stale).

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

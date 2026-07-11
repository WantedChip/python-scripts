# .env Auditor

Compares a `.env` file with `.env.example`, Docker Compose files, and source code to identify missing, undocumented, unused, or unknown environment variables — **without exposing secret values**.

## Features

- **Undocumented Variables**: In `.env` but missing from `.env.example`.
- **Missing Locally**: In `.env.example` but absent from local `.env`.
- **Unused Variables**: Declared in env files but never referenced in source code or Docker files.
- **Unknown Variables**: Referenced in source code but not declared anywhere.
- **Docker Compose Integration**: Parses `docker-compose.yml` / `compose.yaml` for `${VAR}` references.
- **Secret-Safe**: Values are **never displayed** — only variable names appear in output.

## Requirements

No third-party dependencies. Requires Python 3.9+.

## Usage

```bash
# Audit the current directory (auto-detects .env, .env.example, docker-compose.yml)
python env_auditor.py

# Specify custom paths
python env_auditor.py --env .env.production --example .env.example --source ./src

# Custom Docker Compose files
python env_auditor.py --docker docker-compose.yml docker-compose.prod.yml

# Fail (exit code 1) if issues are found — useful in CI
python env_auditor.py --fail-on-issues

# Verbose mode
python env_auditor.py -v
```

## Options

| Argument | Description | Default |
|---|---|---|
| `--env FILE` | Path to the `.env` file | `.env` |
| `--example FILE` | Path to `.env.example` | `.env.example` |
| `--source DIR` | Root directory for source code scan | `.` |
| `--extensions EXT...` | File extensions to scan | `.py .js .ts .go ...` |
| `--exclude DIR...` | Directories to skip | `node_modules .venv dist` |
| `--docker FILE...` | Docker Compose file(s) (auto-detected) | auto |
| `--fail-on-issues` | Exit code 1 if any issues found | False |
| `-v, --verbose` | Verbose logging | False |

## Notes

- The tool auto-detects `docker-compose*.yml` / `compose*.yaml` in the source root.
- Only uppercase identifiers matching `[A-Z_][A-Z0-9_]*` are considered valid variable names.
- Variable usage detection covers Python (`os.environ`, `os.getenv`), JavaScript/Node (`process.env`), shell (`${VAR}`), Ruby (`ENV['VAR']`), PHP/C (`getenv`), Java (`System.getenv`), and Rust (`std::env::var`).

## Running Tests

```bash
pytest
```

Quality: pylint 10.00/10 · 97% coverage · 0 dependencies

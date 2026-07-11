# Project Bootstrapper

A CLI scaffolding utility to generate clean Python project structures, standard development dependencies configurations (linters, typecheckers, formatter, testing engines), and automated Github Actions CI workflows.

## Features

- **Safe Directory Scaffolding**: Automatically cleans non-alphanumeric directory names and converts them to safe import-compliant Python module folder layout mappings.
- **Preconfigured Linting Rules**: Generates `pyproject.toml` containing black, isort, and pytest configurations.
- **Predefined Development Requirements**: Generates `requirements-dev.txt` detailing black, isort, flake8, pylint, mypy, pytest, and coverage plugins.
- **Github Actions CI Workflows**: Generates matrix-based YAML configurations under `.github/workflows/` testing Python versions on Windows, Ubuntu, and macOS.
- **No Overwrite Safety**: Prevents accidental directory overrides unless explicitly using the `--force` flag.
- **Zero Dependencies**: Relies exclusively on Python's standard library.

## Scaffold Structure

Generated layout for project `--name "My Project"`:

```text
MyProject/
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   └── myproject/
│       ├── __init__.py
│       └── main.py
├── tests/
│   ├── __init__.py
│   └── test_main.py
├── .gitignore
├── pyproject.toml
├── README.md
└── requirements-dev.txt
```

## Usage

```bash
# Generate project scaffold with Github Actions CI
python project_bootstrapper.py -n "My App"

# Generate project template inside custom directory, skipping CI workflow
python project_bootstrapper.py -n "Core Util" -o ./projects/ --ci none

# Scaffolding summary details
python project_bootstrapper.py --help
```

## Requirements

- Python 3.x (standard library only)

# readme-doctor

Verify README setup and installation code blocks in a strictly isolated, clean Python virtual environment (`venv`) to identify obsolete dependencies, invalid flags, and stale instructions.

## Usage

Extract and verify code blocks from the local `README.md` file:

```bash
python readme_doctor.py
```

Audit a custom README/Setup markdown file path:

```bash
python readme_doctor.py C:/Users/Name/Projects/my_app/docs/INSTALLATION.md
```

Extract instructions without initializing execution runs:

```bash
python readme_doctor.py --dry-run
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Execution Behavior

- Automatically parses Markdown code blocks marked with shell languages.
- Spawns an isolated Python `venv` virtual environment in a temporary directory.
- Copies local project setup configurations to the sandbox workspace.
- Reroutes `python` and `pip` command calls to use the local virtual environment executables, ensuring complete system package isolation.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

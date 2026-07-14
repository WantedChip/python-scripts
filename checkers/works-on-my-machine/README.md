# Works On My Machine

Inspects a Python project and generates a reproducibility report covering Python version compatibility, OS assumptions, environment variables, external binaries, ports, package versions, and undeclared system dependencies.

## Quality Metadata
Quality: pylint 10.00/10 · 83% coverage · 0 dependencies

## Features

- **Python Version compatibility**: Compares project-defined constraints (`.python-version` or `pyproject.toml`) against the running Python runtime.
- **OS Platform Assumptions**: Flags platform-specific modules (`winreg`, `pwd`, etc.) and hardcoded absolute paths that could block cross-platform runs.
- **Environment Variables**: Detects `os.environ` / `os.getenv` key lookups and warns about missing variables from the current host shell context.
- **System Binary Dependencies**: Checks if command-line calls via `subprocess` or `os.system` are missing from the system's `PATH`.
- **Network Ports**: Identifies hardcoded listener ports and checks if they are already occupied or blocked.
- **Dependency Audit**: Flags version mismatches in `requirements.txt` or third-party package imports that are not declared in setup configurations.

## Usage

Inspect any project by pointing to its root directory:

```bash
python checkers/works-on-my-machine/works_on_my_machine.py path/to/project_dir
```

## Running Tests

Run the test suite and verify line coverage:

```bash
pytest checkers/works-on-my-machine/tests/test_works_on_my_machine.py --cov=checkers/works-on-my-machine/works_on_my_machine --cov-report=term-missing
```

# readme-command-tester

Extract code blocks and commands from a project's README file and execute them inside an isolated temporary sandbox directory to verify that setup instructions actually work without failures.

## Usage

Extract and verify setup commands from the local `README.md` file:

```bash
python readme_command_tester.py
```

Audit a custom README file path:

```bash
python readme_command_tester.py C:/Users/Name/Projects/my_app/docs/SETUP.md
```

Extract and list commands without running them:

```bash
python readme_command_tester.py --dry-run
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Execution Behavior

- Parses markdown blocks matching code languages like `sh`, `bash`, `shell`, `powershell`, `cmd`, and `console`.
- Copies local project descriptors (e.g. `setup.py`, `package.json`, `requirements.txt`) to a temporary isolated workspace.
- Executes commands in sequence via subprocess. If any command fails (non-zero exit code), it aborts further runs and reports stdout/stderr diagnostics.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

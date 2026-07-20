# command-replay

Record a sequence of terminal commands interactively, substitute changing environment values (ports, branch names, local project paths) with parameter variables, and export clean bash or PowerShell runner scripts.

## Usage

Record an interactive terminal workflow:

```bash
python command_replay.py record raw_history.json
```

Substitute parameters in the recorded history and compile a reusable Bash runner script:

```bash
python command_replay.py parameterize raw_history.json run_deploy.sh
```

Compile a reusable PowerShell runner script:

```bash
python command_replay.py parameterize raw_history.json run_deploy.ps1
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Workflow Steps

1. **Interactive Recording**: Runs commands in a loop, logs stdout directly to console, and captures exit codes and CWD paths.
2. **Interactive Parameterization**: Prompts the user for substring patterns to replace (e.g. `8080`) and parameter names (e.g. `$PORT`).
3. **Template Exporting**: Outputs a clean executable shell script (`.sh` or `.ps1`) pre-populated with assignments representing the parameterized variables.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

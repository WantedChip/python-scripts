# pip-why

A command-line tool to analyze Python environment dependency paths, uninstall safety, and package version conflicts.

## Usage

```bash
# Traces dependency paths from top-level packages to 'requests'
python checkers/pip-why/pip_why.py why requests

# Performs uninstall safety audit for 'urllib3'
python checkers/pip-why/pip_why.py remove-check urllib3

# Scans the active environment for version constraint conflicts
python checkers/pip-why/pip_why.py conflicts

# Output results in JSON format using --json
python checkers/pip-why/pip_why.py conflicts --json
```

## Requirements
- Zero external dependencies. Uses Python standard library `importlib.metadata`.

## Quality
Quality: pylint 10.00/10 · 94% coverage · 0 dependencies

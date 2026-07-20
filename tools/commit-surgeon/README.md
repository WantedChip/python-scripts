# commit-surgeon

Analyze Git working tree modifications, build dependency mappings among modified files using import analysis, and suggest logical Git commits to split large monolithic commits.

## Usage

Inspect current working directory dirty files and get staging group suggestions:

```bash
python commit_surgeon.py
```

Inspect a target Git repository directory path:

```bash
python commit_surgeon.py C:/Users/Name/Projects/my_app
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)
- Git command line tool installed on system PATH

## Commits Grouping Logic

- **Configurations/Manifests**: Groups setup manifests, `.gitignore`, and package dependency lists.
- **Core Components**: Groups lower-level modified modules and files that are imported by other files but import nothing modified themselves.
- **Application Logic**: Groups higher-level orchestration code and entry points.
- **Tests & Docs**: Groups test cases and markdown documentation files.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

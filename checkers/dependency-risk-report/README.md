# dependency-risk-report

Audits dependency requirements configuration files (e.g. `requirements.txt`) against PyPI package registries to evaluate version gaps, Python version requirements, and SemVer upgrade risk profiles.

## Usage

Run an audit on the default local `requirements.txt` file:

```bash
python dependency_risk_report.py
```

Audit a custom requirements configuration path:

```bash
python dependency_risk_report.py C:/Users/Name/Projects/my_app/requirements-dev.txt
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)
- Active internet connection (to connect to PyPI JSON API endpoint service queries)

## Risk Levels Scored

- **High**: Major version changes (e.g. 1.x to 2.x). Breaking API changes, method removal, and compatibility shifts are highly probable.
- **Medium**: Minor version upgrades (e.g. 1.2.x to 1.3.x). Adds new features and parameters; minor deprecation warnings and behavior modifications are possible.
- **Low**: Patch updates (e.g. 1.2.3 to 1.2.4). Focuses on bug fixes and performance corrections. Safe to upgrade immediately.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

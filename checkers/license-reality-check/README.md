# license-reality-check

Scan package dependencies and identify potential open-source license compatibility and compliance problems before distributing or sharing a project.

## Usage

Audit package licenses listed in the local `requirements.txt` file:

```bash
python license_reality_check.py
```

Audit a custom requirements configuration path:

```bash
python license_reality_check.py C:/Users/Name/Projects/my_app/requirements-prod.txt
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)
- Active internet connection (to connect to PyPI JSON API endpoint service queries)

## License Risks Evaluated

- **Permissive**: Safe open-source licenses (MIT, BSD, Apache-2.0, ISC, CC0, Public Domain). Free to distribute commercially.
- **High Risk**: Restrictive copyleft licenses (GPL, AGPL, LGPL, MPL, CDDL). May enforce source code disclosure constraints.
- **Needs Review**: Unclassified, custom, or hybrid licenses. Manual review recommended.
- **Warning**: License details not discovered in package metadata classifiers.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

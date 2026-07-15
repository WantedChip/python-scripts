# command-doctor

A diagnostic linter and rules engine that analyzes failed process commands or stderr log dumps to locate execution obstacles and recommend resolutions.

## Usage

```bash
# Runs command and diagnoses if it exits non-zero
python checkers/command-doctor/command_doctor.py -c "python scripts/missing_package.py"

# Diagnoses a pre-existing stderr log dump directly
python checkers/command-doctor/command_doctor.py -s error.log
```

## Diagnostics Checked
1. **Missing executable**: Verifies if command program exists in system PATH.
2. **Missing file arguments**: Check existence of referenced path parameters in CWD.
3. **Permissions**: Audits files access status on permission failure errors.
4. **Port conflicts**: Inspects system socket connections via `psutil` to show PID/name details of process holding target port.
5. **Virtual environment anomalies**: Alerts when running global interpreters when local venvs exist, and checks for python import issues.
6. **PATH warnings**: Lists duplicate or invalid paths within system PATH configuration.

## Requirements
- Third-party packages: `psutil==7.2.2`.

## Quality
Quality: pylint 10.00/10 · 84% coverage · 1 dependency

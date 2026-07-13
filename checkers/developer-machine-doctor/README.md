# Developer Machine Doctor

Diagnose environment configurations, virtualenv settings, binary paths, port bindings, disk space, and file permissions on your local development machine.

## Usage

```bash
# Run complete diagnostic checks and print text summary
python src/developer_machine_doctor/main.py

# Run diagnostics and output structured JSON data
python src/developer_machine_doctor/main.py --json

# Diagnose specific ports
python src/developer_machine_doctor/main.py --ports 3000,5000,8000,8080
```

## Features

- **PATH Env Check**: Identifies duplicated, broken, or empty paths in the system `PATH` variable.
- **Python Environment**: Reports python interpreter path, version, virtualenv state, and checks for tools (`pip`, `uv`, `poetry`, `conda`, `pipenv`).
- **Dependency Scan**: Verifies if development commands like `git`, `curl`, `docker`, `node`, `npm`, `gcc`, `make`, and `ssh` are callable.
- **Port Conflict Scan**: Inspects if web development ports are occupied and maps them to process names, PIDs, owners, and arguments.
- **Disk Space Check**: Evaluates storage volume limits and utilization ratios.
- **Process Privileges**: Validates administrative privilege state and checks write capabilities.

## Requirements

- Python 3.10+
- `psutil>=5.9.8` (for port process details)

Quality: pylint 10.00/10 · 100% coverage · 1 dependencies

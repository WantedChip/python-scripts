# port-conflict-doctor

Troubleshoot port conflicts ("address already in use") by identifying the process PID, name, parent process name, current working directory, command line, and Docker container mappings, and recommending the safest stop instructions.

## Usage

Diagnose conflict status for a specific port (e.g. 8080):

```bash
python port_conflict_doctor.py 8080
```

List active listening ports and prompt for a port choice:

```bash
python port_conflict_doctor.py
```

## Requirements

- Python 3.11+
- `psutil` (listed in [requirements.txt](requirements.txt) to query TCP sockets and parent PIDs)
- Docker command line client (optional, to check container mappings)

## Diagnostics Conducted

- **Docker Mappings**: Checks `docker ps` port bindings to identify container conflicts.
- **Process Lineage**: Resolves process ID, binary name, working folder, and parent task.
- **Remediation Guides**: Outputs the exact OS-specific termination commands (`kill` or `taskkill`).

## Quality

Quality: pylint 10.00/10 · 100% coverage · 1 dependency

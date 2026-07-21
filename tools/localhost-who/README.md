# localhost-who

Show every development service currently running on localhost: project name, port, process owner PID, uptime, working folder, health check state, and the exact launch command.

## Usage

List all active development services:

```bash
python localhost_who.py
```

## Requirements

- Python 3.11+
- `psutil` (listed in [requirements.txt](requirements.txt) to audit active listening TCP ports and resolve process details)

## Diagnostics Performed

- **Port Scans**: Interrogates TCP sockets to find listening ports in the common development ranges.
- **Process Lineage**: Resolves process PID, command line, working directory, and creation times to compute uptimes.
- **HTTP Probe Checks**: Sends a fast HTTP probe to the port to evaluate response headers and status codes.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 1 dependency

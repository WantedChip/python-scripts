# localhost-dashboard

Consolidate and monitor active local development servers in a unified terminal dashboard. It scans system ports, maps host processes, guesses frameworks based on project assets, and performs local HTTP probes to verify responsiveness.

## Usage

Output a single status overview report:

```bash
python localhost_dashboard.py
```

Run in continuous watch mode, refreshing statistics every 3 seconds:

```bash
python localhost_dashboard.py --watch
```

## Requirements

- Python 3.11+
- `psutil` (listed in [requirements.txt](requirements.txt) to query system port mappings)

## Capabilities

- **Port Scans**: Focuses on local TCP listeners bound to localhost (`127.0.0.1`, `::1`, `0.0.0.0`) in typical development port ranges (e.g. 3000-9999).
- **Framework Heuristics**: Analyzes process Working Directories for build and environment assets (e.g., `package.json` -> Next/Vite, `requirements.txt` -> Python FastAPI, `go.mod` -> Go server, etc.).
- **Health Checks**: Sends HTTP GET requests to listening endpoints with 0.5s timeouts, reporting latency, response codes, and unresponsive status.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 1 dependency

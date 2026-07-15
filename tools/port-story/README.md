# port-story

A comprehensive port diagnostics and inspection tool that reports connection owners, start times, parent ancestries, and environment variable profiles, and applies heuristics to classify dev servers, docker proxies, system daemons, and databases.

## Usage

```bash
# Audits all active LISTEN ports on TCP/UDP
python tools/port-story/port_story.py

# Audits specifically ports 8000 and 9000
python tools/port-story/port_story.py 8000 9000

# Audits ports and returns a structured JSON dump
python tools/port-story/port_story.py 8000 --json

# Audits ports and prints env var maps (sanitized of sensitive keys)
python tools/port-story/port_story.py 8000 --verbose
```

## Classification Heuristics
1. **Docker**: Flags when connection is owned by `docker-proxy` or parent processes contain `docker`/`containerd`.
2. **Dev Server**: Flags when command arguments match dev frameworks like `webpack`, `vite`, `django`, `flask`, `next.js`, or reference local virtual environments.
3. **Database**: Detects database daemons like `postgres`, `mysqld`, `redis-server`, or `mongod`.
4. **System Service**: Identifies core services run by `root` / `SYSTEM` users or directly launched by systemd/launchd.

## Requirements
- Third-party packages: `psutil==7.2.2`.

## Quality
Quality: pylint 10.00/10 · 86% coverage · 1 dependency

# Port Availability Checker

A Python command-line utility to test TCP and UDP port status on local or remote target hosts with custom timeouts and concurrent scanning.

## Features
- TCP and UDP protocol checks.
- Flexible port specifications (single ports, comma-separated lists, ranges like `8000-8010`).
- Multi-threaded parallel scanning.
- Summary table or JSON output mode (`--json`).

## Requirements
Standard Python library (3.8+). No external dependencies.

## Usage
```bash
python main.py 127.0.0.1 -p 80,443,8000-8005 --protocol TCP --timeout 1.5
```

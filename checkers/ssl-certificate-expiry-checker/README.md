# SSL/TLS Certificate Expiry Checker

A Python command-line tool to check SSL/TLS certificate expiration dates for domains and issue warning alerts if expiry is within N days.

## Features
- Fetches `notAfter` expiration timestamp using standard library `ssl` & `socket`.
- Configurable warning threshold in days (`-w / --warning-days`).
- Clean ASCII table or JSON output format (`--json`).
- Non-zero exit code if warnings or errors are detected (useful for CI/CD or monitoring scripts).

## Installation & Requirements
Requires Python 3.8+. No external dependencies needed.

```bash
python main.py google.com github.com:443 -w 30
```

## Usage
```bash
python main.py example.com --json
```

# Log File Analyzer

A Python CLI tool to parse and analyze Nginx/Apache web server access logs in Common or Combined Log Format.

## Features

- Parses log entries (IP address, timestamp, HTTP method/path, status code, response size in bytes)
- Aggregates top IP addresses, status codes, top requested paths, and bandwidth usage
- Renders a clean terminal dashboard summary
- Export options for JSON and multi-section CSV reports

## Usage

```bash
python main.py /var/log/nginx/access.log
python main.py access.log --json summary.json
python main.py access.log --csv summary.csv
```

## Running Tests

```bash
python -m unittest discover -s tests
```

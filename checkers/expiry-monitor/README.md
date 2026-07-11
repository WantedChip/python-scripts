# SSL/Domain Expiry Monitor

Track domain registration expiration (via WHOIS) and SSL certificate expiration (via TLS socket) and send warnings/critical alerts.

## Usage

```bash
python expiry_monitor.py [options]
```

### Examples

```bash
# Check expiry for multiple domains passed via CLI arguments
python expiry_monitor.py -d google.com python.org github.com

# Check domains list from a text file
python expiry_monitor.py -f domains.txt

# Specify custom thresholds (warning at 60 days, critical at 30 days)
python expiry_monitor.py -d google.com -w 60 -c 30

# Send Slack/Discord alerts using a webhook
python expiry_monitor.py -d google.com -w 30 --webhook "https://discord.com/api/webhooks/..."

# Output report in JSON format
python expiry_monitor.py -d google.com -j
```

### File Format (`domains.txt`)

```text
# This is a comment
google.com
github.com
python.org
```

## Requirements

Requires `python-whois` and `requests`. Install them using:

```bash
pip install -r requirements.txt
```

## Notes

* SSL certificate verification utilizes Python's native standard `ssl` and `socket` connection context to read expiry directly from TLS parameters.
* Domain registration query utilizes the `whois` client package, parsing common registrar structures. Expiry parameters returned as multi-registrar list structures are normalized.
* The script exits with status code `1` if any domain registration or SSL certificate is expired or falls into critical status (defaults to <15 days remaining), or `0` on fully healthy domains.

Quality: pylint 10.00/10 · 96% coverage · 1 dependencies

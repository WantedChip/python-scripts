# WHOIS Domain Scraper

A lightweight Python tool to perform WHOIS & RDAP lookups on domain names. Parses registrar metadata, creation/expiration dates, name servers, status flags, and calculates days until domain expiration.

## Features

- Primary lookup using standard **RDAP (Registration Data Access Protocol)** JSON API.
- Fallback to raw TCP **WHOIS socket query** (port 43).
- Structured parsing across multiple TLD WHOIS text formats.
- Expiration date tracking with days-left countdown.
- Output in tabular format or JSON format.

## Usage

### Single Domain Lookup
```bash
python main.py --domain example.com
```

### Batch Lookup from File
```bash
python main.py --file domains.txt --format json --output report.json
```

### Run Tests
```bash
python -m unittest discover -s tests
```

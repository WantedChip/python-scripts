# python-scripts

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)
![Status: active](https://img.shields.io/badge/status-active-brightgreen.svg)

A growing collection of standalone Python scripts, organized by category.
Each script lives in its own folder with its own short README, so you can
grab just what you need without digging through the whole repo.

## Structure

```
python-scripts/
├── scraping/
├── automation/
├── checkers/
├── tools/
├── converters/
├── api-wrappers/
├── misc/
└── ...
```

Each script folder looks like:

```
category-name/script-name/
├── script_name.py
├── requirements.txt   # if it has external dependencies
└── README.md          # what it does + how to run it
```

## Index

<!-- Update this list whenever a script is added. One line per script. -->

| Category | Script | Description |
|---|---|---|
| `automation` | [device-monitor](automation/device-monitor/) | Tracks local network host joins and leaves via ping sweeps and cross-platform ARP table parsing. |
| `automation` | [downloads-organizer](automation/downloads-organizer/) | Watches/scans a folder and sorts files into subfolders by extension, filename, date, or custom rules. |
| `automation` | [smart-backup](automation/smart-backup/) | Incremental backups with checksums, exclusions, retention policies, verification, and dry-run mode. |
| `automation` | [website-monitor](automation/website-monitor/) | Watches specific webpage sections via CSS selectors and sends alerts on meaningful content updates. |
| `checkers` | [api-monitor](checkers/api-monitor/) | Periodically tests HTTP endpoints for status codes, latency thresholds, JSON schemas, and SSL expiry. |
| `checkers` | [config-validator](checkers/config-validator/) | Validates JSON/YAML configurations against schemas and generates compiler-like human-readable error messages. |
| `checkers` | [env-auditor](checkers/env-auditor/) | Compares `.env`, `.env.example`, Docker files, and source code to find missing or unused variables. |
| `checkers` | [expiry-monitor](checkers/expiry-monitor/) | Evaluates domain WHOIS registration and SSL certificate validity days remaining. |
| `checkers` | [link-checker](checkers/link-checker/) | Crawls a website or scans local Markdown/HTML files and reports dead links, redirects, and timeouts. |
| `tools` | [csv-cleaner](tools/csv-cleaner/) | Detects encoding, delimiter, duplicates, malformed dates, empty columns, and type problems in CSVs. |
| `tools` | [duplicate-finder](tools/duplicate-finder/) | Scans directories for duplicate files by content hash and optionally moves them to quarantine. |
| `tools` | [file-renamer](tools/file-renamer/) | Bulk rename with regex, numbering, date cleanup, preview mode, and full undo/rollback support. |
| `tools` | [folder-snapshot](tools/folder-snapshot/) | Records a directory's state as a JSON snapshot and diffs two snapshots to show changes. |
| `tools` | [git-cleanup](tools/git-cleanup/) | Finds large files, stale branches, ignored junk, and accidentally committed secrets in a git repo. |
| `tools` | [log-analyzer](tools/log-analyzer/) | Parses large log files line-by-line, masks variables to group error occurrences, and flags rate spikes. |
| `tools` | [port-inspector](tools/port-inspector/) | Audits listening/active network ports, displays process owner metadata, and kills target processes safely. |
| `tools` | [space-investigator](tools/space-investigator/) | Explains what consumes storage, detects unusually large folders, and exports a report. |

## Usage

Each script is self-contained. To run one:

```bash
cd category-name/script-name
pip install -r requirements.txt   # only if present
python script_name.py
```

## License

Licensed under the [MIT License](LICENSE).

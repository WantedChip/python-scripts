# Script Index

Full index of every script in this repo, organized by category.

## Table of Contents
- [automation](#automation)
- [checkers](#checkers)
- [tools](#tools)

---

## automation

| Script | Description |
|---|---|
| [device-monitor](automation/device-monitor/) | Tracks local network host joins and leaves via ping sweeps and cross-platform ARP table parsing. |
| [downloads-organizer](automation/downloads-organizer/) | Watches/scans a folder and sorts files into subfolders by extension, filename, date, or custom rules. |
| [smart-backup](automation/smart-backup/) | Incremental backups with checksums, exclusions, retention policies, verification, and dry-run mode. |
| [website-monitor](automation/website-monitor/) | Watches specific webpage sections via CSS selectors and sends alerts on meaningful content updates. |

---

## checkers

| Script | Description |
|---|---|
| [api-monitor](checkers/api-monitor/) | Periodically tests HTTP endpoints for status codes, latency thresholds, JSON schemas, and SSL expiry. |
| [config-validator](checkers/config-validator/) | Validates JSON/YAML configurations against schemas and generates compiler-like human-readable error messages. |
| [cron-health-checker](checkers/cron-health-checker/) | Detect failed, missing, overlapping, or silently broken scheduled jobs. |
| [dep-reporter](checkers/dep-reporter/) | Scan projects for outdated packages, breaking-version risks, and changelog links. |
| [env-auditor](checkers/env-auditor/) | Compares `.env`, `.env.example`, Docker files, and source code to find missing or unused variables. |
| [expiry-monitor](checkers/expiry-monitor/) | Evaluates domain WHOIS registration and SSL certificate validity days remaining. |
| [link-checker](checkers/link-checker/) | Crawls a website or scans local Markdown/HTML files and reports dead links, redirects, and timeouts. |
| [sqlite-inspector](checkers/sqlite-inspector/) | Audit SQLite databases, summarizing tables, null patterns, duplicate rows, and schema issues. |

---

## tools

| Script | Description |
|---|---|
| [csv-cleaner](tools/csv-cleaner/) | Detects encoding, delimiter, duplicates, malformed dates, empty columns, and type problems in CSVs. |
| [data-export-searcher](tools/data-export-searcher/) | Search archives from chat apps, email, or social platforms locally with advanced query filters. |
| [data-pipeline-diff](tools/data-pipeline-diff/) | Compare two CSV, JSON, or database outputs and explain exactly what changed. |
| [duplicate-finder](tools/duplicate-finder/) | Scans directories for duplicate files by content hash and optionally moves them to quarantine. |
| [expense-parser](tools/expense-parser/) | Parse messy bank-export CSVs into normalized categories and monthly spending summaries. |
| [file-renamer](tools/file-renamer/) | Bulk rename with regex, numbering, date cleanup, preview mode, and full undo/rollback support. |
| [folder-snapshot](tools/folder-snapshot/) | Records a directory's state as a JSON snapshot and diffs two snapshots to show changes. |
| [git-cleanup](tools/git-cleanup/) | Finds large files, stale branches, ignored junk, and accidentally committed secrets in a git repo. |
| [history-analyzer](tools/history-analyzer/) | Analyze shell history locally to find frequent commands and suggest aliases. |
| [image-optimizer](tools/image-optimizer/) | Recursively resize, compress, and convert images while preserving originals and metadata. |
| [local-document-search](tools/local-document-search/) | Privacy-first full-text search for local files — index and search documents without uploading. |
| [log-analyzer](tools/log-analyzer/) | Parses large log files line-by-line, masks variables to group error occurrences, and flags rate spikes. |
| [pdf-toolkit](tools/pdf-toolkit/) | Merge, split, rotate, extract, compress, and rename PDFs from one CLI. |
| [port-inspector](tools/port-inspector/) | Audits listening/active network ports, displays process owner metadata, and kills target processes safely. |
| [project-bootstrapper](tools/project-bootstrapper/) | Generate custom Python structures with standard linters, pytest configurations, and GitHub CI workflow matrix. |
| [screenshot-organizer](tools/screenshot-organizer/) | Sorts screenshots by date, OCR text content, app/window clues, and duplicate similarity. |
| [space-investigator](tools/space-investigator/) | Explains what consumes storage, detects unusually large folders, and exports a report. |
| [subtitle-fixer](tools/subtitle-fixer/) | Shift timing, repair encoding, remove duplicates, and convert subtitle formats (SRT/VTT/ASS). |

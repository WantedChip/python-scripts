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
| [ai-code-sanitizer](checkers/ai-code-sanitizer/) | Scan code likely generated or heavily modified by AI and flag fake imports, nonexistent package APIs, duplicate helpers, placeholder comments, swallowed exceptions, unnecessary abstractions, and tests that don't really test anything. |
| [api-monitor](checkers/api-monitor/) | Periodically tests HTTP endpoints for status codes, latency thresholds, JSON schemas, and SSL expiry. |
| [command-doctor](checkers/command-doctor/) | Diagnose failed command executions using a diagnostic rules engine. |
| [config-validator](checkers/config-validator/) | Validates JSON/YAML configurations against schemas and generates compiler-like human-readable error messages. |
| [cron-health-checker](checkers/cron-health-checker/) | Detect failed, missing, overlapping, or silently broken scheduled jobs. |
| [dep-reporter](checkers/dep-reporter/) | Scan projects for outdated packages, breaking-version risks, and changelog links. |
| [developer-machine-doctor](checkers/developer-machine-doctor/) | Diagnose PATH issues, Python environments, missing dependencies, port conflicts, disk problems, and permissions. |
| [env-auditor](checkers/env-auditor/) | Compares `.env`, `.env.example`, Docker files, and source code to find missing or unused variables. |
| [env-diff](checkers/env-diff/) | Compare local and target environments to debug execution mismatches. |
| [gitignore-explain](checkers/gitignore-explain/) | Explain exactly which rule ignored a file, where that rule came from, and how to fix it. |
| [expiry-monitor](checkers/expiry-monitor/) | Evaluates domain WHOIS registration and SSL certificate validity days remaining. |
| [link-checker](checkers/link-checker/) | Crawls a website or scans local Markdown/HTML files and reports dead links, redirects, and timeouts. |
| [pip-why](checkers/pip-why/) | Audits why Python packages are installed, who depends on them, and version conflicts. |
| [repo-doctor](checkers/repo-doctor/) | Run one command inside any repository and detect missing README sections, broken setup commands, stale dependencies, missing .gitignore entries, giant files, accidental binaries, dead links, and suspicious secrets. |
| [repository-documentation-auditor](checkers/repository-documentation-auditor/) | Detect missing setup instructions, dead commands, undocumented environment variables, and stale README references. |
| [secret-leak-scanner](checkers/secret-leak-scanner/) | Detect sensitive API keys, credentials, database connection strings, and private SSH keys in local files or git staged commits, providing remediation steps. |
| [sqlite-inspector](checkers/sqlite-inspector/) | Audit SQLite databases, summarizing tables, null patterns, duplicate rows, and schema issues. |
| [works-on-my-machine](checkers/works-on-my-machine/) | Inspect a Python project and generate a reproducibility report covering Python version, OS assumptions, environment variables, external binaries, ports, package versions, and undeclared system dependencies. |

---

## tools

| Script | Description |
|---|---|
| [api-response-recorder](tools/api-response-recorder/) | Save sanitized API responses and turn them into deterministic fixtures for tests. |
| [branch-graveyard](tools/branch-graveyard/) | Find local and remote branches that are merged, abandoned, duplicated, or attached to closed PRs, with a safe interactive cleanup mode. |
| [changelog-from-reality](tools/changelog-from-reality/) | Compare releases or tags and generate a factual changelog from actual code changes rather than relying only on commit-message quality. |
| [cli-workflow-recorder](tools/cli-workflow-recorder/) | Record a sequence of terminal tasks and turn it into a reusable, parameterized workflow. |
| [config-migration-tool](tools/config-migration-tool/) | Convert old configuration schemas to new versions with automatic backups and migration reports. |
| [commit-splitter](tools/commit-splitter/) | Analyze a messy working tree and suggest logical groups of files or hunks that should become separate commits. |
| [csv-cleaner](tools/csv-cleaner/) | Detects encoding, delimiter, duplicates, malformed dates, empty columns, and type problems in CSVs. |
| [data-export-searcher](tools/data-export-searcher/) | Search archives from chat apps, email, or social platforms locally with advanced query filters. |
| [data-pipeline-diff](tools/data-pipeline-diff/) | Compare two CSV, JSON, or database outputs and explain exactly what changed. |
| [duplicate-finder](tools/duplicate-finder/) | Scans directories for duplicate files by content hash and optionally moves them to quarantine. |
| [error-bundler](tools/error-bundler/) | Bundle command outputs, tracebacks, environment context, and logs into a sanitized ZIP. |
| [expense-parser](tools/expense-parser/) | Parse messy bank-export CSVs into normalized categories and monthly spending summaries. |
| [file-quarantine-cleaner](tools/file-quarantine-cleaner/) | Identify old installers, archives, cache files, and abandoned downloads, but require confirmation before deletion. |
| [file-renamer](tools/file-renamer/) | Bulk rename with regex, numbering, date cleanup, preview mode, and full undo/rollback support. |
| [folder-snapshot](tools/folder-snapshot/) | Records a directory's state as a JSON snapshot and diffs two snapshots to show changes. |
| [fresh-machine](tools/fresh-machine/) | Export your developer setup (packages, Git config, shell aliases, editor extensions, Python tools) and recreate it elsewhere. |
| [gift-idea-generator](tools/gift-idea-generator/) | Suggests personalized gift ideas based on recipient age, budget, relationship, and interests. |
| [git-cleanup](tools/git-cleanup/) | Finds large files, stale branches, ignored junk, and accidentally committed secrets in a git repo. |
| [git-time-machine](tools/git-time-machine/) | Automate Git history investigations to find when config values changed, when dependencies were introduced, and when files grew beyond size limits. |
| [history-analyzer](tools/history-analyzer/) | Analyze shell history locally to find frequent commands and suggest aliases. |
| [image-optimizer](tools/image-optimizer/) | Recursively resize, compress, and convert images while preserving originals and metadata. |
| [issue-reproducer](tools/issue-reproducer/) | Unpack a bug ZIP bundle, recreate its virtual environment, and run the failed command to reproduce the issue. |
| [local-document-search](tools/local-document-search/) | Privacy-first full-text search for local files — index and search documents without uploading. |
| [log-analyzer](tools/log-analyzer/) | Parses large log files line-by-line, masks variables to group error occurrences, and flags rate spikes. |
| [pdf-toolkit](tools/pdf-toolkit/) | Merge, split, rotate, extract, compress, and rename PDFs from one CLI. |
| [port-inspector](tools/port-inspector/) | Audits listening/active network ports, displays process owner metadata, and kills target processes safely. |
| [port-story](tools/port-story/) | Trace process ancestry, cmdline, CWD, and heuristics (Docker, dev servers) of port owners. |
| [project-bootstrapper](tools/project-bootstrapper/) | Generate custom Python structures with standard linters, pytest configurations, and GitHub CI workflow matrix. |
| [random-name-generator](tools/random-name-generator/) | Generates randomized name suggestions for people, projects, and pets with optional alliteration. |
| [repo-size-history](tools/repo-size-history/) | Show exactly when a repository became bloated and which commits/files caused the growth. |
| [recipe-scaler-tool](tools/recipe-scaler-tool/) | Scales recipe ingredient quantities with metric/imperial conversion and fraction formatting. |
| [screenshot-organizer](tools/screenshot-organizer/) | Sorts screenshots by date, OCR text content, app/window clues, and duplicate similarity. |
| [space-investigator](tools/space-investigator/) | Explains what consumes storage, detects unusually large folders, and exports a report. |
| [subtitle-fixer](tools/subtitle-fixer/) | Shift timing, repair encoding, remove duplicates, and convert subtitle formats (SRT/VTT/ASS). |
| [system-change-tracker](tools/system-change-tracker/) | Snapshot and diff system state (directories, environment variables, Python/OS packages, services) to audit what was modified during an installation. |
| [travel-itinerary-planner](tools/travel-itinerary-planner/) | Builds customized day-by-day travel itineraries based on budget, style, and pace constraints. |
| [universal-export-converter](tools/universal-export-converter/) | Normalize exports from different services into clean JSON/CSV with a plugin architecture. |
| [webhook-debugger](tools/webhook-debugger/) | Receive webhooks locally, inspect headers/payloads, replay requests, and compare deliveries. |
| [workout-plan-generator](tools/workout-plan-generator/) | Generates personalized weekly workout programs tailored to fitness goals, skill level, and equipment. |

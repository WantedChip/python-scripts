# Script Index

Full index of every script in this repo, organized by category.

## Table of Contents
- [api-wrappers](#api-wrappers)
- [automation](#automation)
- [checkers](#checkers)
- [tools](#tools)

---

## api-wrappers

| Script | Description |
|---|---|
| [bitcoin-price-fetcher](api-wrappers/bitcoin-price-fetcher/) | Retrieves current Bitcoin/crypto price, market cap, and 24h change from CoinGecko API with fallback support. |
| [cat-fact-fetcher](api-wrappers/cat-fact-fetcher/) | Fetches random cat facts from Cat Facts API and accumulates them into a local collection file with deduplication. |
| [cocktail-recipe-fetcher](api-wrappers/cocktail-recipe-fetcher/) | Searches cocktail recipes by name or ingredient using TheCocktailDB API and formats recipe cards. |
| [country-info-fetcher](api-wrappers/country-info-fetcher/) | Retrieves country data (capital, population, region, flag URL, currency, languages) from REST Countries API. |
| [exchange-rate-fetcher](api-wrappers/exchange-rate-fetcher/) | Fetches real-time and historical exchange rates between currencies from a free API. |
| [github-user-info-fetcher](api-wrappers/github-user-info-fetcher/) | Fetches GitHub user profile metrics, public repo count, top language breakdown, and total stars. |
| [ip-geolocation-lookup](api-wrappers/ip-geolocation-lookup/) | Geolocation lookup for IP addresses (country, city, ISP, lat/lon, timezone) via free IP APIs. |
| [joke-fetcher](api-wrappers/joke-fetcher/) | Retrieves programming or general jokes from JokeAPI with category filters and safe mode. |
| [nasa-apod-fetcher](api-wrappers/nasa-apod-fetcher/) | Downloads NASA Astronomy Picture of the Day images and exports metadata descriptions to Markdown notes. |
| [pokemon-info-fetcher](api-wrappers/pokemon-info-fetcher/) | Looks up Pokémon stats, abilities, types, sprite URLs, and evolution chains from PokéAPI. |

---

## automation

| Script | Description |
|---|---|
| [device-monitor](automation/device-monitor/) | Tracks local network host joins and leaves via ping sweeps and cross-platform ARP table parsing. |
| [download-intent](automation/download-intent/) | Organize downloads based on filename context keywords, with confidence scores and SQLite transaction undo. |
| [downloads-organizer](automation/downloads-organizer/) | Watches/scans a folder and sorts files into subfolders by extension, filename, date, or custom rules. |
| [smart-backup](automation/smart-backup/) | Incremental backups with checksums, exclusions, retention policies, verification, and dry-run mode. |
| [website-monitor](automation/website-monitor/) | Watches specific webpage sections via CSS selectors and sends alerts on meaningful content updates. |

---

## checkers

| Script | Description |
|---|---|
| [ai-code-sanitizer](checkers/ai-code-sanitizer/) | Scan code likely generated or heavily modified by AI and flag fake imports, nonexistent package APIs, duplicate helpers, placeholder comments, swallowed exceptions, unnecessary abstractions, and tests that don't really test anything. |
| [api-contract-diff](checkers/api-contract-diff/) | Compare two API versions (OpenAPI/Swagger) and report client-breaking changes. |
| [api-monitor](checkers/api-monitor/) | Periodically tests HTTP endpoints for status codes, latency thresholds, JSON schemas, and SSL expiry. |
| [command-doctor](checkers/command-doctor/) | Diagnose failed command executions using a diagnostic rules engine. |
| [cleanup-simulator](checkers/cleanup-simulator/) | Let cleanup scripts describe exactly what they would delete and how much space they would recover before doing anything. |
| [config-archaeologist](checkers/config-archaeologist/) | Find old configuration files left behind by uninstalled software and explain why they are probably stale. |
| [config-validator](checkers/config-validator/) | Validates JSON/YAML configurations against schemas and generates compiler-like human-readable error messages. |
| [cron-health-checker](checkers/cron-health-checker/) | Detect failed, missing, overlapping, or silently broken scheduled jobs. |
| [csv-autopsy](checkers/csv-autopsy/) | Explain why a CSV file is broken: encodings, quoting, column counts, control characters, dates, and numbers. |
| [dead-code-confidence](checkers/dead-code-confidence/) | Find functions, modules, CLI flags, and config options that appear unused, but provide evidence and confidence rather than deleting anything. |
| [dep-reporter](checkers/dep-reporter/) | Scan projects for outdated packages, breaking-version risks, and changelog links. |
| [dependency-risk-report](checkers/dependency-risk-report/) | Assess update risks in requirement configurations, checking SemVer version gaps, Python version compatibilities, and vulnerabilities. |
| [developer-machine-doctor](checkers/developer-machine-doctor/) | Diagnose PATH issues, Python environments, missing dependencies, port conflicts, disk problems, and permissions. |
| [docs-drift](checkers/docs-drift/) | Find references in docs to files, commands, config keys, API names, and versions that no longer exist. |
| [env-auditor](checkers/env-auditor/) | Compares `.env`, `.env.example`, Docker files, and source code to find missing or unused variables. |
| [env-diff](checkers/env-diff/) | Compare local and target environments to debug execution mismatches. |
| [env-requirements](checkers/env-requirements/) | Scan source, Docker files, CI, configs, and docs to identify required, undocumented, or stale env variables. |
| [example-drift-checker](checkers/example-drift-checker/) | Detect when code examples in docs no longer match the current API. |
| [expiry-monitor](checkers/expiry-monitor/) | Evaluates domain WHOIS registration and SSL certificate validity days remaining. |
| [gitignore-explain](checkers/gitignore-explain/) | Explain exactly which rule ignored a file, where that rule came from, and how to fix it. |
| [json-shape](checkers/json-shape/) | Feed thousands of JSON records and get a report of common fields, types, anomalies, and schema drift. |
| [license-reality-check](checkers/license-reality-check/) | Scan dependencies and identify license compatibility problems before a project is distributed. |
| [link-checker](checkers/link-checker/) | Crawls a website or scans local Markdown/HTML files and reports dead links, redirects, and timeouts. |
| [orphan-config](checkers/orphan-config/) | Find config files and application-data folders probably left behind by software that is no longer installed. |
| [pip-why](checkers/pip-why/) | Audits why Python packages are installed, who depends on them, and version conflicts. |
| [permission-explainer](checkers/permission-explainer/) | Explain Unix/Windows file-permission problems in normal language and suggest the smallest safe fix. |
| [privacy-report](checkers/privacy-report/) | Scan a folder before sharing or uploading it and flag EXIF GPS data, usernames in paths, email addresses, API keys, hidden files, and document metadata. |
| [readme-command-tester](checkers/readme-command-tester/) | Extract shell commands from a README and test whether the documented setup actually works in a clean environment. |
| [readme-doctor](checkers/readme-doctor/) | Extract commands from a README, execute them in an isolated virtual environment, and report which instructions are stale. |
| [repo-doctor](checkers/repo-doctor/) | Run one command inside any repository and detect missing README sections, broken setup commands, stale dependencies, missing .gitignore entries, giant files, accidental binaries, dead links, and suspicious secrets. |
| [repository-documentation-auditor](checkers/repository-documentation-auditor/) | Detect missing setup instructions, dead commands, undocumented environment variables, and stale README references. |
| [scheduled-task-auditor](checkers/scheduled-task-auditor/) | Unified view of cron, systemd timers, Windows Task Scheduler, and startup scripts, with detection of broken commands and missing paths. |
| [schema-drift](checkers/schema-drift/) | Compare batches of JSON/API responses over time and show fields that appeared, disappeared, changed type, or became unexpectedly nullable. |
| [secret-history-check](checkers/secret-history-check/) | Check whether a secret was merely deleted from the current file or still exists in Git history. |
| [secret-leak-scanner](checkers/secret-leak-scanner/) | Detect sensitive API keys, credentials, database connection strings, and private SSH keys in local files or git staged commits, providing remediation steps. |
| [setup-diff](checkers/setup-diff/) | Compare two developer machines and explain why the project works on A but fails on B: runtime versions, binaries, environment-variable presence, PATH, permissions, package versions, ports, and config. |
| [sqlite-inspector](checkers/sqlite-inspector/) | Audit SQLite databases, summarizing tables, null patterns, duplicate rows, and schema issues. |
| [stash-conflict-preview](checkers/stash-conflict-preview/) | Before git stash apply, estimate which files and hunks are likely to conflict. |
| [test-gap](checkers/test-gap/) | Compare changed code with executed tests and report important changed paths that were never exercised. |
| [workflow-lint-plus](checkers/workflow-lint-plus/) | Find duplicate jobs, unpinned actions, impossible conditions, unnecessary matrix combinations, missing timeouts, and cache mistakes. |
| [works-on-my-machine](checkers/works-on-my-machine/) | Inspect a Python project and generate a reproducibility report covering Python version, OS assumptions, environment variables, external binaries, ports, package versions, and undeclared system dependencies. |

---

## tools

| Script | Description |
|---|---|
| [api-response-recorder](tools/api-response-recorder/) | Save sanitized API responses and turn them into deterministic fixtures for tests. |
| [archive-before-delete](tools/archive-before-delete/) | Wrap dangerous deletion commands by creating a recoverable manifest or quarantine first. |
| [branch-graveyard](tools/branch-graveyard/) | Find local and remote branches that are merged, abandoned, duplicated, or attached to closed PRs, with a safe interactive cleanup mode. |
| [branch-memory](tools/branch-memory/) | For every branch, generate a compact summary of what was being accomplished there from commits, dirty changes, TODOs, and issues. |
| [changelog-from-reality](tools/changelog-from-reality/) | Compare releases or tags and generate a factual changelog from actual code changes rather than relying only on commit-message quality. |
| [ci-failure-deduper](tools/ci-failure-deduper/) | Group multiple CI log failures by root cause instead of making developers inspect jobs separately. |
| [ci-local](tools/ci-local/) | Translate a GHA CI workflow to local reproduction command lines. |
| [ci-log-deduper](tools/ci-log-deduper/) | Parse multiple failed CI logs, collapse dynamic tokens, and group them into root failure signatures. |
| [cli-workflow-recorder](tools/cli-workflow-recorder/) | Record a sequence of terminal tasks and turn it into a reusable, parameterized workflow. |
| [command-replay](tools/command-replay/) | Record a terminal workflow, replace changing values with parameters, and turn it into a reusable, inspectable script. |
| [commit-splitter](tools/commit-splitter/) | Analyze a messy working tree and suggest logical groups of files or hunks that should become separate commits. |
| [commit-surgeon](tools/commit-surgeon/) | Take a messy working tree and suggest logical commit groups by file dependency and diff relationship. |
| [config-map](tools/config-map/) | Scan a project and compile a resolution map of CLI, Env, and local settings configurations. |
| [config-migration-tool](tools/config-migration-tool/) | Convert old configuration schemas to new versions with automatic backups and migration reports. |
| [context-switch](tools/context-switch/) | Save your complete development context before switching tasks: current branch, dirty changes, running dev servers, open ports, recent commands, notes, and TODOs. |
| [csv-cleaner](tools/csv-cleaner/) | Detects encoding, delimiter, duplicates, malformed dates, empty columns, and type problems in CSVs. |
| [curl-to-test](tools/curl-to-test/) | Convert cURL commands into requests snippets, pytest tests, mock fixtures, and markdown docs. |
| [data-diff-human](tools/data-diff-human/) | Compare CSV/JSON records and summarize changes in a clean, human-friendly format. |
| [data-export-searcher](tools/data-export-searcher/) | Search archives from chat apps, email, or social platforms locally with advanced query filters. |
| [data-peek](tools/data-peek/) | One command to inspect CSV, TSV, JSON, JSONL, Parquet, SQLite, and Excel: schema, row count, nulls, sample values, suspicious columns, and basic stats. |
| [data-pipeline-diff](tools/data-pipeline-diff/) | Compare two CSV, JSON, or database outputs and explain exactly what changed. |
| [dependency-change-impact](tools/dependency-change-impact/) | Scan project codebase using Python AST before upgrading a dependency to locate affected imports and breaking API call sites. |
| [dependency-why](tools/dependency-why/) | Display dependency chains, project components importing a package, and consequences of removing it. |
| [diff-story](tools/diff-story/) | Turn a large Git diff patch into a structured narrative: behavioral edits, refactors, dependencies, and risk flags. |
| [document-deduper](tools/document-deduper/) | Detect near-duplicate PDFs and documents even when filenames and metadata differ. |
| [duplicate-finder](tools/duplicate-finder/) | Scans directories for duplicate files by content hash and optionally moves them to quarantine. |
| [error-bundler](tools/error-bundler/) | Bundle command outputs, tracebacks, environment context, and logs into a sanitized ZIP. |
| [expense-parser](tools/expense-parser/) | Parse messy bank-export CSVs into normalized categories and monthly spending summaries. |
| [failure-pack](tools/failure-pack/) | Run a failing command and create a sanitized diagnostic bundle containing stdout, stderr, exit code, OS, package versions, env keys, config, and logs. |
| [file-origin](tools/file-origin/) | Track where a downloaded file originated using Zone.Identifier and local browser history download searches. |
| [file-quarantine-cleaner](tools/file-quarantine-cleaner/) | Identify old installers, archives, cache files, and abandoned downloads, but require confirmation before deletion. |
| [file-renamer](tools/file-renamer/) | Bulk rename with regex, numbering, date cleanup, preview mode, and full undo/rollback support. |
| [fixture-shrinker](tools/fixture-shrinker/) | Reduce a giant JSON, CSV, or text file to the smallest input that still reproduces a bug. |
| [flaky-test-hunter](tools/flaky-test-hunter/) | Run tests repeatedly with randomized ordering/timing to rank flaky tests. |
| [folder-snapshot](tools/folder-snapshot/) | Records a directory's state as a JSON snapshot and diffs two snapshots to show changes. |
| [fresh-machine](tools/fresh-machine/) | Export your developer setup (packages, Git config, shell aliases, editor extensions, Python tools) and recreate it elsewhere. |
| [gift-idea-generator](tools/gift-idea-generator/) | Suggests personalized gift ideas based on recipient age, budget, relationship, and interests. |
| [git-cleanup](tools/git-cleanup/) | Finds large files, stale branches, ignored junk, and accidentally committed secrets in a git repo. |
| [git-time-machine](tools/git-time-machine/) | Automate Git history investigations to find when config values changed, when dependencies were introduced, and when files grew beyond size limits. |
| [git-undo-explain](tools/git-undo-explain/) | Explain the safest Git operation for mistakes, show the exact effect visually, then optionally execute it. |
| [history-analyzer](tools/history-analyzer/) | Analyze shell history locally to find frequent commands and suggest aliases. |
| [image-optimizer](tools/image-optimizer/) | Recursively resize, compress, and convert images while preserving originals and metadata. |
| [issue-reproducer](tools/issue-reproducer/) | Unpack a bug ZIP bundle, recreate its virtual environment, and run the failed command to reproduce the issue. |
| [local-document-search](tools/local-document-search/) | Privacy-first full-text search for local files — index and search documents without uploading. |
| [localhost-dashboard](tools/localhost-dashboard/) | Detect local dev servers and show them in one terminal UI: ports, projects, processes, uptime, and health. |
| [localhost-who](tools/localhost-who/) | Show active development service ports, PID runtimes, working directories, launch commands, and HTTP health. |
| [log-analyzer](tools/log-analyzer/) | Parses large log files line-by-line, masks variables to group error occurrences, and flags rate spikes. |
| [log-merge](tools/log-merge/) | Give it logs from multiple services, normalize timestamps, sort events into one timeline, collapse duplicate errors, and show context. |
| [mock-from-traffic](tools/mock-from-traffic/) | Record application dev traffic, sanitize credentials and fields, and save local mock response files. |
| [minimal-reproducer](tools/minimal-reproducer/) | Automatically shrink a failing JSON, CSV, or config file to find the smallest input reproducing a failure. |
| [pdf-toolkit](tools/pdf-toolkit/) | Merge, split, rotate, extract, compress, and rename PDFs from one CLI. |
| [port-conflict-doctor](tools/port-conflict-doctor/) | Diagnose 'address already in use' port conflicts, explaining process owners and recommending safe kills. |
| [port-inspector](tools/port-inspector/) | Audits listening/active network ports, displays process owner metadata, and kills target processes safely. |
| [port-story](tools/port-story/) | Trace process ancestry, cmdline, CWD, and heuristics (Docker, dev servers) of port owners. |
| [process-family-tree](tools/process-family-tree/) | Show why a mystery background process exists by tracing its parent, launch command, working directory, network connections, and child processes. |
| [project-bootstrapper](tools/project-bootstrapper/) | Generate custom Python structures with standard linters, pytest configurations, and GitHub CI workflow matrix. |
| [project-resume](tools/project-resume/) | Enter an old project directory after six months and get: what it does, how to run it, last changes, unfinished TODOs, broken dependencies, and likely next steps. |
| [random-name-generator](tools/random-name-generator/) | Generates randomized name suggestions for people, projects, and pets with optional alliteration. |
| [repo-bloat-timeline](tools/repo-bloat-timeline/) | Pinpoint when a Git repository grew in size, which commits caused size spikes, and top blob contributors. |
| [repo-size-history](tools/repo-size-history/) | Show exactly when a repository became bloated and which commits/files caused the growth. |
| [recipe-scaler-tool](tools/recipe-scaler-tool/) | Scales recipe ingredient quantities with metric/imperial conversion and fraction formatting. |
| [receipt-normalizer](tools/receipt-normalizer/) | Take messy exported receipts or invoice PDFs and produce standardized local CSV/JSON records. |
| [safe-undo](tools/safe-undo/) | A wrapper/library other Python scripts can use for destructive filesystem operations: writes a transaction manifest, then rollback reverses it. |
| [screenshot-organizer](tools/screenshot-organizer/) | Sorts screenshots by date, OCR text content, app/window clues, and duplicate similarity. |
| [screenshot-search](tools/screenshot-search/) | OCR a screenshot folder locally and let users search things like "error about Docker" or "receipt from June." |
| [share-safe](tools/share-safe/) | Create sanitized copies of logs and project folders for bug reports, automatically replacing home-directory names, tokens, IPs, and selected identifiers. |
| [space-investigator](tools/space-investigator/) | Explains what consumes storage, detects unusually large folders, and exports a report. |
| [stash-manager](tools/stash-manager/) | Git stash manager showing source branch, age, changed files, conflict risk, and safe preview before apply. |
| [subtitle-fixer](tools/subtitle-fixer/) | Shift timing, repair encoding, remove duplicates, and convert subtitle formats (SRT/VTT/ASS). |
| [system-change-tracker](tools/system-change-tracker/) | Snapshot and diff system state (directories, environment variables, Python/OS packages, services) to audit what was modified during an installation. |
| [test-order-hunter](tools/test-order-hunter/) | Randomize test execution order repeatedly to detect order-dependent flaky tests and culprit state polluters. |
| [travel-itinerary-planner](tools/travel-itinerary-planner/) | Builds customized day-by-day travel itineraries based on budget, style, and pace constraints. |
| [universal-export-converter](tools/universal-export-converter/) | Normalize exports from different services into clean JSON/CSV with a plugin architecture. |
| [webhook-debugger](tools/webhook-debugger/) | Receive webhooks locally, inspect headers/payloads, replay requests, and compare deliveries. |
| [webhook-lab](tools/webhook-lab/) | Local webhook receiver with request history, payload diffing, replay, signature verification, and secret redaction. |
| [why-is-this-file-here](tools/why-is-this-file-here/) | Given any project file, explain when it appeared, which commit introduced it, who references it, whether it is generated, whether it is ignored, and whether it appears safe to remove. |
| [workout-plan-generator](tools/workout-plan-generator/) | Generates personalized weekly workout programs tailored to fitness goals, skill level, and equipment. |
| [worktree-manager](tools/worktree-manager/) | Git worktree manager: create worktrees, check disk usage, detect abandoned checkouts, and clean metadata safely. |

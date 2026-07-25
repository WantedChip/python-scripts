# Script Index

Full index of every script in this repo, organized by category.

## Table of Contents
- [api-wrappers](#api-wrappers)
- [automation](#automation)
- [checkers](#checkers)
- [converters](#converters)
- [scraping](#scraping)
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
| [public-holiday-fetcher](api-wrappers/public-holiday-fetcher/) | Fetches national/public holidays for any country and year using Nager.Date API. |
| [random-quote-fetcher](api-wrappers/random-quote-fetcher/) | Fetches random inspirational, tech, or famous quotes from Quotable API with fallback engine. |
| [random-user-generator](api-wrappers/random-user-generator/) | Generates realistic mock user profiles (name, email, address, picture) from RandomUser.me API. |
| [university-search-fetcher](api-wrappers/university-search-fetcher/) | Searches universities worldwide by country or name using HipoLabs University Domains API. |
| [zipcode-info-fetcher](api-wrappers/zipcode-info-fetcher/) | Retrieves location metadata (city, state, coordinates) for postal codes via Zippopotam.us API. |

---

## automation

| Script | Description |
|---|---|
| [backup-rotation-manager](automation/backup-rotation-manager/) | Enforces backup retention policies (daily/weekly/monthly rotations) and cleans up expired backups. |
| [cpu-load-monitor](automation/cpu-load-monitor/) | Records CPU load averages and per-core utilization at intervals, generating a summary report. |
| [device-monitor](automation/device-monitor/) | Tracks local network host joins and leaves via ping sweeps and cross-platform ARP table parsing. |
| [directory-watcher](automation/directory-watcher/) | Real-time filesystem event monitor watching file creations, modifications, and deletions. |
| [disk-usage-monitor](automation/disk-usage-monitor/) | Monitors disk space usage across mounts and triggers warning alerts/logs when free space drops. |
| [download-intent](automation/download-intent/) | Organize downloads based on filename context keywords, with confidence scores and SQLite transaction undo. |
| [downloads-folder-organizer](automation/downloads-folder-organizer/) | Categorizes loose files in downloads folder by file extensions, MIME types, and date modified. |
| [downloads-organizer](automation/downloads-organizer/) | Watches/scans a folder and sorts files into subfolders by extension, filename, date, or custom rules. |
| [empty-folder-cleaner](automation/empty-folder-cleaner/) | Recursively identifies and removes empty directories with dry-run mode, path exclusion, and logging support. |
| [memory-usage-monitor](automation/memory-usage-monitor/) | Monitors RAM and swap space utilization, logs usage trends, and sends threshold alerts. |
| [smart-backup](automation/smart-backup/) | Incremental backups with checksums, exclusions, retention policies, verification, and dry-run mode. |
| [website-monitor](automation/website-monitor/) | Watches specific webpage sections via CSS selectors and sends alerts on meaningful content updates. |

---

## checkers

| Script | Description |
|---|---|
| [ai-code-sanitizer](checkers/ai-code-sanitizer/) | Scan code likely generated or heavily modified by AI and flag fake imports, nonexistent package APIs, duplicate helpers, placeholder comments, swallowed exceptions, unnecessary abstractions, and tests that don't really test anything. |
| [api-contract-diff](checkers/api-contract-diff/) | Compare two API versions (OpenAPI/Swagger) and report client-breaking changes. |
| [api-monitor](checkers/api-monitor/) | Periodically tests HTTP endpoints for status codes, latency thresholds, JSON schemas, and SSL expiry. |
| [assumption-hunter](checkers/assumption-hunter/) | AST analyzer that flags unvalidated assumptions (unhandled Nones, unverified dict keys, raw indexing, unchecked status codes). |
| [command-doctor](checkers/command-doctor/) | Diagnose failed command executions using a diagnostic rules engine. |
| [cleanup-simulator](checkers/cleanup-simulator/) | Let cleanup scripts describe exactly what they would delete and how much space they would recover before doing anything. |
| [config-archaeologist](checkers/config-archaeologist/) | Find old configuration files left behind by uninstalled software and explain why they are probably stale. |
| [config-validator](checkers/config-validator/) | Validates JSON/YAML configurations against schemas and generates compiler-like human-readable error messages. |
| [copy-drift](checkers/copy-drift/) | Structural code similarity checker detecting copy-pasted Python logic across modules using tokenized Jaccard similarity. |
| [cron-doctor](checkers/cron-doctor/) | Diagnostic engine auditing cron schedules for syntax errors, missing binary paths, overlapping jobs, and permission issues. |
| [cron-health-checker](checkers/cron-health-checker/) | Detect failed, missing, overlapping, or silently broken scheduled jobs. |
| [cron-job-validator](checkers/cron-job-validator/) | Validates 5-field cron syntax expressions, computes future execution schedules, and detects schedule overlap conflicts. |
| [csv-autopsy](checkers/csv-autopsy/) | Explain why a CSV file is broken: encodings, quoting, column counts, control characters, dates, and numbers. |
| [csv-forensics](checkers/csv-forensics/) | Deep forensic audit tool for CSV file integrity, encoding defects, control characters, broken quoting, and Excel corruption. |
| [dead-code-confidence](checkers/dead-code-confidence/) | Find functions, modules, CLI flags, and config options that appear unused, but provide evidence and confidence rather than deleting anything. |
| [dep-reporter](checkers/dep-reporter/) | Scan projects for outdated packages, breaking-version risks, and changelog links. |
| [dependency-risk-report](checkers/dependency-risk-report/) | Assess update risks in requirement configurations, checking SemVer version gaps, Python version compatibilities, and vulnerabilities. |
| [developer-machine-doctor](checkers/developer-machine-doctor/) | Diagnose PATH issues, Python environments, missing dependencies, port conflicts, disk problems, and permissions. |
| [docs-drift](checkers/docs-drift/) | Find references in docs to files, commands, config keys, API names, and versions that no longer exist. |
| [email-validator-cleaner](checkers/email-validator-cleaner/) | Validates and cleans email addresses in CSV files with syntax regex, disposable domain detection, and DNS checks. |
| [env-auditor](checkers/env-auditor/) | Compares `.env`, `.env.example`, Docker files, and source code to find missing or unused variables. |
| [env-diff](checkers/env-diff/) | Compare local and target environments to debug execution mismatches. |
| [env-requirements](checkers/env-requirements/) | Scan source, Docker files, CI, configs, and docs to identify required, undocumented, or stale env variables. |
| [epub-doctor](checkers/epub-doctor/) | Diagnostic tool for EPUB archives checking XML syntax, broken internal links/anchors, missing metadata, and oversized images. |
| [example-drift-checker](checkers/example-drift-checker/) | Detect when code examples in docs no longer match the current API. |
| [expiry-monitor](checkers/expiry-monitor/) | Evaluates domain WHOIS registration and SSL certificate validity days remaining. |
| [file-share-audit](checkers/file-share-audit/) | Audits directory trees before sharing/uploading to flag API keys, credentials, EXIF GPS data, and path usernames. |
| [folder-permission-reporter](checkers/folder-permission-reporter/) | Recursively scans folders for insecure, overly permissive (777, world-writable), or irregular file permissions. |
| [generated-file-check](checkers/generated-file-check/) | Identifies committed generated build artifacts, minified assets, auto-generated code, and lock files. |
| [gitignore-explain](checkers/gitignore-explain/) | Explain exactly which rule ignored a file, where that rule came from, and how to fix it. |
| [hotfix-debt](checkers/hotfix-debt/) | Scans repository codebase for temporary hotfix tags, inline workarounds, emergency patches, and overdue tech debt markers. |
| [intent-expiry](checkers/intent-expiry/) | Scans codebase for temporary developer annotations, TODOs, and fixmes with expiration target dates or version triggers. |
| [json-shape](checkers/json-shape/) | Feed thousands of JSON records and get a report of common fields, types, anomalies, and schema drift. |
| [json-shape-diff](checkers/json-shape-diff/) | Compare structure and data shapes of two JSON files/APIs to highlight added, removed, or type-shifted schema fields. |
| [license-reality-check](checkers/license-reality-check/) | Scan dependencies and identify license compatibility problems before a project is distributed. |
| [link-checker](checkers/link-checker/) | Crawls a website or scans local Markdown/HTML files and reports dead links, redirects, and timeouts. |
| [machine-bootstrap-audit](checkers/machine-bootstrap-audit/) | Audits machine bootstrap and setup scripts (shell & Python) statically for hidden interactive prompts, un-checked binaries, and hardcoded paths. |
| [orphan-config](checkers/orphan-config/) | Find config files and application-data folders probably left behind by software that is no longer installed. |
| [outlier-detector-csv](checkers/outlier-detector-csv/) | Flags statistical outliers in numeric CSV columns using IQR (Interquartile Range) or Z-score detection methods. |
| [output-drift](checkers/output-drift/) | Validates Markdown documentation code block outputs against actual execution results and highlights drifted snippets. |
| [pip-why](checkers/pip-why/) | Audits why Python packages are installed, who depends on them, and version conflicts. |
| [permission-explainer](checkers/permission-explainer/) | Explain Unix/Windows file-permission problems in normal language and suggest the smallest safe fix. |
| [plagiarism-detector](checkers/plagiarism-detector/) | Compares two text documents and reports similarity metrics using N-gram containment and TF-IDF / term frequency cosine distance. |
| [port-availability-checker](checkers/port-availability-checker/) | Scans single ports or port ranges across TCP/UDP protocols for local or remote hosts with custom timeout configuration and structured tabular/JSON reporting. |
| [privacy-report](checkers/privacy-report/) | Scan a folder before sharing or uploading it and flag EXIF GPS data, usernames in paths, email addresses, API keys, hidden files, and document metadata. |
| [readme-command-tester](checkers/readme-command-tester/) | Extract shell commands from a README and test whether the documented setup actually works in a clean environment. |
| [readme-doctor](checkers/readme-doctor/) | Extract commands from a README, execute them in an isolated virtual environment, and report which instructions are stale. |
| [repo-doctor](checkers/repo-doctor/) | Run one command inside any repository and detect missing README sections, broken setup commands, stale dependencies, missing .gitignore entries, giant files, accidental binaries, dead links, and suspicious secrets. |
| [repository-documentation-auditor](checkers/repository-documentation-auditor/) | Detect missing setup instructions, dead commands, undocumented environment variables, and stale README references. |
| [scheduled-task-auditor](checkers/scheduled-task-auditor/) | Unified view of cron, systemd timers, Windows Task Scheduler, and startup scripts, with detection of broken commands and missing paths. |
| [schema-drift](checkers/schema-drift/) | Compare batches of JSON/API responses over time and show fields that appeared, disappeared, changed type, or became unexpectedly nullable. |
| [secret-deleted-or-not](checkers/secret-deleted-or-not/) | Analyzes git commit history to determine whether a sensitive pattern was completely deleted or remains in earlier commits. |
| [secret-history-check](checkers/secret-history-check/) | Check whether a secret was merely deleted from the current file or still exists in Git history. |
| [secret-leak-scanner](checkers/secret-leak-scanner/) | Detect sensitive API keys, credentials, database connection strings, and private SSH keys in local files or git staged commits, providing remediation steps. |
| [service-status-checker](checkers/service-status-checker/) | Inspects local system services and process states across systemd and psutil with tabular or JSON status reporting. |
| [setup-diff](checkers/setup-diff/) | Compare two developer machines and explain why the project works on A but fails on B: runtime versions, binaries, environment-variable presence, PATH, permissions, package versions, ports, and config. |
| [sqlite-inspector](checkers/sqlite-inspector/) | Audit SQLite databases, summarizing tables, null patterns, duplicate rows, and schema issues. |
| [ssl-certificate-expiry-checker](checkers/ssl-certificate-expiry-checker/) | Checks SSL/TLS certificate expiration dates for target domains and alerts if expiry falls within a specified threshold. |
| [stash-conflict-preview](checkers/stash-conflict-preview/) | Before git stash apply, estimate which files and hunks are likely to conflict. |
| [test-gap](checkers/test-gap/) | Compare changed code with executed tests and report important changed paths that were never exercised. |
| [time-sync-auditor](checkers/time-sync-auditor/) | Audits NTP and chrony synchronization health across multi-host Linux environments or parses time sync CLI logs. |
| [workflow-lint-plus](checkers/workflow-lint-plus/) | Find duplicate jobs, unpinned actions, impossible conditions, unnecessary matrix combinations, missing timeouts, and cache mistakes. |
| [works-on-my-machine](checkers/works-on-my-machine/) | Inspect a Python project and generate a reproducibility report covering Python version, OS assumptions, environment variables, external binaries, ports, package versions, and undeclared system dependencies. |

---

## converters

| Script | Description |
|---|---|
| [csv-column-reorder](converters/csv-column-reorder/) | Reorders, selects, or drops columns in CSV files based on a specified header sequence or JSON configuration file. |
| [currency-normalizer](converters/currency-normalizer/) | Normalizes mixed currency strings into standardized decimal float numbers and ISO 4217 currency codes. |
| [date-format-standardizer](converters/date-format-standardizer/) | Detects inconsistent date/time strings in CSV columns and standardizes them to ISO 8601 (YYYY-MM-DD). |
| [json-flatten-nested](converters/json-flatten-nested/) | Flattens deeply nested JSON structures and arrays into a single-level flat dictionary format and supports CSV export. |
| [json-to-csv-converter](converters/json-to-csv-converter/) | Converts JSON object arrays or JSON lines (JSONL) files into CSV format with automatic column header collection. |
| [markdown-to-html-converter](converters/markdown-to-html-converter/) | Converts Markdown documents into standalone HTML pages with basic syntax support and CSS styling templates. |
| [null-value-filler](converters/null-value-filler/) | Fills missing or null values in CSV columns using strategies like constant value, forward fill, backward fill, mean, or median. |
| [phone-number-formatter](converters/phone-number-formatter/) | Formats raw phone numbers into standardized international E.164, national, or custom formats using country codes. |
| [text-case-converter](converters/text-case-converter/) | Converts text or file content between various casing styles (snake_case, camelCase, PascalCase, kebab-case, UPPERCASE, lowercase, Title Case, CONSTANT_CASE). |
| [text-encoding-converter](converters/text-encoding-converter/) | Detects and converts text file character encodings (e.g. UTF-8, Latin-1, Windows-1252, ASCII) to target encodings with BOM and error handling. |

---

## scraping

| Script | Description |
|---|---|
| [academic-paper-scraper](scraping/academic-paper-scraper/) | Searches arXiv for academic papers by keyword or category, extracts metadata, BibTeX citations, and optional PDF downloads. |
| [book-info-scraper](scraping/book-info-scraper/) | Looks up book metadata (title, author, date, publisher, pages, subjects) by ISBN using the Open Library API. |
| [documentation-scraper](scraping/documentation-scraper/) | Crawls documentation sites and builds a single consolidated offline HTML or Markdown reference with Table of Contents. |
| [event-listing-scraper](scraping/event-listing-scraper/) | Parses event listings from JSON-LD schema, iCalendar (.ics), and HTML feeds, supporting filtering and export. |
| [github-trending-scraper](scraping/github-trending-scraper/) | Fetches trending repositories on GitHub by programming language and timeframe, exporting to Markdown, JSON, or ASCII tables. |
| [news-headline-scraper](scraping/news-headline-scraper/) | Scrapes top news headlines from RSS/Atom feeds or web pages with keyword filtering and Markdown/JSON export. |
| [podcast-episode-scraper](scraping/podcast-episode-scraper/) | Scrapes podcast RSS feeds, parses episode metadata, and downloads MP3 audio files. |
| [product-review-scraper](scraping/product-review-scraper/) | Scrapes e-commerce product reviews from HTML/JSON, calculating rating distributions and sentiment metrics. |
| [quote-of-the-day-scraper](scraping/quote-of-the-day-scraper/) | Scrapes daily motivational quotes from web sources or API fallback into JSON or formatted cards. |
| [real-estate-listing-scraper](scraping/real-estate-listing-scraper/) | Scrapes property real estate listings, parsing price, bedrooms, bathrooms, address, and specs into CSV/JSON. |
| [recipe-scraper](scraping/recipe-scraper/) | Scrapes recipe web pages or Schema.org JSON-LD to extract title, prep time, ingredients, and instructions. |
| [stock-price-scraper](scraping/stock-price-scraper/) | Fetches current stock quotes, calculates price changes, and appends historical data to a CSV log. |
| [weather-scraper](scraping/weather-scraper/) | Fetches current weather reports and forecasts for cities or coordinates via public APIs. |
| [whois-domain-scraper](scraping/whois-domain-scraper/) | Performs WHOIS/RDAP domain lookups, parsing registrar info, expiration dates, and days until expiry. |

---

## tools

| Script | Description |
|---|---|
| [agent-boundary](tools/agent-boundary/) | Maintains a hunk-level provenance ledger for human vs AI coding agent edits to report contributions and scope violations. |
| [api-response-recorder](tools/api-response-recorder/) | Save sanitized API responses and turn them into deterministic fixtures for tests. |
| [archive-before-delete](tools/archive-before-delete/) | Wrap dangerous deletion commands by creating a recoverable manifest or quarantine first. |
| [artifact-recipe](tools/artifact-recipe/) | Records build provenance for generated files into sidecar recipes and explains artifact staleness. |
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

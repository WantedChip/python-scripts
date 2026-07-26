# Bug Report Builder

A CLI utility for generating high-quality, sanitized issue reports from failed command executions or log files.

## Features

- **Command Execution & Capture**: Run any command, record exit status, execution duration, `stdout`, and `stderr`.
- **Log Parsing**: Ingest existing log files or standard input if execution output is already captured.
- **Environment Diagnostics**: Automatically gather OS details, Python version, CLI arguments, and environment variables.
- **Sensitive Data Sanitization**: Auto-redact secrets, API keys, tokens, passwords, AWS credentials, JWTs, and private keys.
- **Attachment Support**: Read and attach sanitized contents of diagnostic log files or text attachments.
- **Multiple Output Formats**: Export clean GitHub-ready Markdown or structured JSON.

## Usage

```bash
# Run a failing command and generate a markdown bug report
python main.py --command "python app.py --invalid-flag" --output report.md

# Build report from log file with expected vs actual behavior notes
python main.py --log-file error.log --expected "Process should exit with 0" --actual "Terminated with exit code 1" --output report.json --format json

# Attach log files with custom title
python main.py --command "npm test" --title "Frontend Test Failure" --attachment debug.log
```

## Options

- `-c`, `--command`: Command string or executable to run and capture.
- `-l`, `--log-file`: Path to an existing log file to include.
- `--expected`: Expected behavior description.
- `--actual`: Actual behavior description.
- `--title`: Custom title for the bug report.
- `--attachment`: File path to attach (can be specified multiple times).
- `-o`, `--output`: Output file path (defaults to stdout).
- `-f`, `--format`: Output format (`markdown` or `json`).
- `--mask-env`: Additional environment variable keys to sanitize.

## Testing

```bash
python -m unittest discover tests
```

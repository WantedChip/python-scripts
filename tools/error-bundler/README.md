# error-bundler

A diagnostic utility that executes commands, catches failures, and securely packages environment state, system metadata, traceback output, local configurations, and logs into a sanitized ZIP archive.

## Usage

```bash
# Execute a command and build a bundle if it fails
python tools/error-bundler/error_bundler.py -c "python scripts/broken.py"

# Build a bundle from a pre-existing traceback file
python tools/error-bundler/error_bundler.py -s error.log -o crash_report.zip

# Customize environment key sanitization list and log files search patterns
python tools/error-bundler/error_bundler.py -c "npm run build" --log-patterns *.log build-err.txt --sanitize-keys MY_SECRET_VAR
```

## Requirements
- Zero external dependencies. Uses Python standard library.

## Quality
Quality: pylint 10.00/10 · 84% coverage · 0 dependencies

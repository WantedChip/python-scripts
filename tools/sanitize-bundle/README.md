# Bundle Sanitizer

`sanitize-bundle` creates a shareable copy of a project or log directory with sensitive information consistently replaced with deterministic placeholders.

## Features

- **Deterministic Replacement**: Maps values like emails (`user@domain.com` -> `[EMAIL_1]`), IPs (`192.168.1.1` -> `[IP_1]`), and user paths (`/home/john` -> `[PATH_1]`) deterministically across all files.
- **Redacts Secrets & Tokens**: Detects and redacts AWS keys, JWTs, Bearer tokens, and generic API keys.
- **Preserves Directory Structure**: Recursively processes all subdirectories and copies binary files intact.

## Usage

```bash
python main.py --src /path/to/logs --dst /path/to/clean_bundle
```

Optional flags:
- `--user <USERNAME>`: Explicitly specify a username string to redact.

## Running Tests

```bash
python -m unittest discover -s tests
```

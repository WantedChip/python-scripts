# Environment Variable Exporter

A Python tool that exports OS environment variables matching prefix filters or specific key lists into formatted, sanitized `.env` files for application setup and template sharing.

## Features
- Filter environment variables by key prefix (e.g. `APP_`, `DATABASE_`) or explicit key lists.
- Secret masking mode (`-m / --mask-secrets`) to replace sensitive values (passwords, tokens, keys) with placeholders.
- Automatic formatting and quoting for multi-word or special character values.

## Installation & Requirements
Standard Python 3.8+. No external dependencies needed.

## Usage
```bash
python main.py -p APP_ -o .env.example --mask-secrets
```

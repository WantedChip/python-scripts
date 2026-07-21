# share-safe

Create sanitized duplicates of log files, debug logs, and project directories before posting them to public issue trackers. It automatically replaces active usernames, home path roots, IP addresses, authorization tokens, password definitions, and user-supplied custom keywords with placeholder markers.

## Usage

Sanitize a directory and copy to a new location:

```bash
python share_safe.py C:/Users/Name/Projects/my_app/logs C:/Users/Name/Projects/my_app/sanitized_logs
```

Dry-run to count matches without writing any files:

```bash
python share_safe.py C:/Users/Name/Projects/my_app/logs C:/Users/Name/Projects/my_app/sanitized_logs --dry-run
```

Add custom sensitive keyword strings to redact:

```bash
python share_safe.py logs/ sanitized_logs/ --custom-redact "MyCompany,InternalProjectName,APIKey_ABC123"
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Redaction Scope

- **Username**: Current login username (`getpass.getuser()`) -> `[USER_REDACTED]`.
- **Home Dir**: Current user home directory root -> `[HOME_REDACTED]`.
- **IP Addresses**: IPv4 and IPv6 patterns -> `[IP_REDACTED]` or `[IPv6_REDACTED]`.
- **Authorizations**: Headers like `Authorization: Bearer <token>` or `Authorization: Basic <credentials>` -> `[TOKEN_REDACTED]`.
- **Secrets**: Assignment variables containing keywords (e.g. `key`, `secret`, `password`, `token`) followed by quotes -> `[REDACTED]`.
- **Custom Keys**: Any keywords passed via `--custom-redact` -> `[REDACTED_KEYWORD]`.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

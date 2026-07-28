# email-attachment-downloader

Downloads attachments from emails matching specific sender, subject, or filename regex filters.

## Usage

### Download PDF Attachments from Specific Sender
```bash
python tools/email-attachment-downloader/email_attachment_downloader.py --host imap.gmail.com -u user@example.com -p "password" --from "reports@company.com" --filename-pattern ".*\.pdf$" -o attachments/
```

## Options
- `--host`: IMAP server host address.
- `--port`: IMAP server port (default: `993`).
- `-u`, `--user`: IMAP account username/email.
- `-p`, `--password`: IMAP password or access token.
- `-m`, `--mailbox`: Target IMAP folder (default: `INBOX`).
- `-o`, `--output-dir`: Local output directory for attachments.
- `--from`: Filter emails from sender address.
- `--subject`: Filter emails containing subject string.
- `--filename-pattern`: Filter attachment filenames with regex (e.g. `.*\.pdf$`).
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- Python 3.10+ (Standard Library)

## Quality
Quality: pylint 10.00/10 · 90% coverage · 0 external dependencies

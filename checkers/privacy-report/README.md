# privacy-report

Scan directories recursively before sharing or uploading them to identify and flag potential privacy leaks (EXIF GPS coordinates, system usernames in file/directory paths or text contents, email addresses, API key secrets, hidden system items, and document metadata).

## Usage

Scan a directory for privacy leaks (default is current folder):

```bash
python privacy_report.py
```

Scan a custom target directory:

```bash
python privacy_report.py C:/Users/Name/Projects/my_app
```

## Requirements

- Python 3.11+
- `Pillow` and `pypdf` (listed in [requirements.txt](requirements.txt) to support image and PDF scans)

## Checks Performed

- **EXIF GPS data**: Flags GPS location metadata coordinates inside image files (`.jpg`, `.jpeg`, `.png`).
- **Usernames**: Automatically queries active system username and scans all directory names, filenames, and text content for occurrences.
- **Emails**: Identifies email patterns using standard regex.
- **Secrets**: Combines keyword detection (e.g. `aws_key`, `secret`, `private_key`) with Shannon entropy checks on line strings to spot randomized token strings.
- **Hidden files**: Identifies dot files and items carrying Windows hidden system flags.
- **Metadata**: Parses PDF metadata for author, creator, and editor names.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 2 dependencies

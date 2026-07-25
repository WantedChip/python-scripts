# File Share Audit Tool

Pre-flight privacy and security auditor to scan folders before uploading or sharing. Detects API keys, secret credentials, `.env` files, `.git` repositories, private log files, user account names in paths, and EXIF GPS tags in images.

## Features
- **API Key & Secret Detection**: Scans files using regex for AWS access keys, OpenAI tokens, GitHub PATs, and generic secret variables.
- **Sensitive File Flagging**: Identifies `.env`, `.pem`, `.key`, `id_rsa`, `.log`, `.git`, and hidden configuration files.
- **EXIF GPS Audit**: Inspects JPEG/TIFF image metadata for geotagged location data.
- **Path Username Detection**: Identifies local OS user account names embedded in paths.
- **Categorized Severity Summary**: Generates clear HIGH, MEDIUM, and LOW severity reports.

## Requirements
```bash
pip install -r requirements.txt
```

## Usage
```bash
python main.py /path/to/target/folder
```

Specify custom username override:
```bash
python main.py /path/to/target/folder --username dev2
```

## Running Tests
```bash
python -m unittest discover tests
```

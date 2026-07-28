# pdf-password-remover

Removes password protection from PDF files given the owner or user password.

## Usage

### Remove Password from Single PDF
```bash
python tools/pdf-password-remover/pdf_password_remover.py encrypted.pdf -p "secret123" -o unlocked.pdf
```

### Remove Password from All PDFs in a Directory
```bash
python tools/pdf-password-remover/pdf_password_remover.py pdf_folder/ -p "secret123" -o unlocked_folder/
```

## Options
- `-p`, `--password`: Owner or user password required for decryption.
- `-o`, `--output`: Destination decrypted output PDF file path or directory.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 85% coverage · 1 dependency

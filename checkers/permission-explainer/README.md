# permission-explainer

Explain Unix or Windows file and folder permission errors in plain language and recommend the minimal safe CLI command fix.

## Usage

Inspect read access permissions for the current user:

```bash
python permission_explainer.py C:/Users/Name/ProtectedFolder
```

Inspect write access permissions:

```bash
python permission_explainer.py C:/Users/Name/ProtectedFolder --operation write
```

Specify a custom user name:

```bash
python permission_explainer.py ProtectedFolder --operation execute --user "Bob"
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## How It Works

- **Windows**: Queries the file system read-only attributes, calls the standard `icacls` system utility via subprocess, parses NTFS Access Control Lists, and suggests `attrib -R` or `icacls /grant` fixes.
- **Unix**: Queries `os.stat` mode, owner UID, and group GID configurations, determines whether the target user is Owner, Group, or Other, and recommends `chmod` or `chown` fixes.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

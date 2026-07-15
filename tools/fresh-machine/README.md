# Fresh Machine Setup Replicator

Export and recreate your developer workstation setup. Walks your Git configurations, shell aliases, editor extensions, system packages, and Python tool lists, exporting them to a portable JSON profile, and automates installation on a fresh system.

## Usage

### Exporting Environment Configuration

```bash
python fresh_machine.py export -o developer_profile.json
```

### Dry Run Import (Preview Installation Scripts)

```bash
python fresh_machine.py import -p developer_profile.json --dry-run
```

### Restoring Environment Configuration

```bash
python fresh_machine.py import -p developer_profile.json
```

## Supported Component Managers

- **Git config**: Collects and writes `--global` config settings.
- **Shell aliases**: Reads custom declarations from `.bashrc`, `.zshrc`, `.bash_profile`, and `.profile` files.
- **VS Code extensions**: Restores extensions list using the `code` CLI.
- **System packages**: Auto-detects and installs via `winget`/`choco` (Windows), `brew` (macOS), and `apt`/`pacman` (Linux).
- **Python tools**: Instores packages using `pipx` or standard `pip`.

## Quality

Quality: pylint 10.00/10 · 92% coverage · 0 dependencies

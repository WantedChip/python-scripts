# gitignore-explain

Explain why a file is ignored by Git, showing the exact pattern, the source file it came from, the line number, and instructions on how to unignore it.

## Usage

```bash
python gitignore_explain.py <file-path> [options]
```

### Options

- `-r`, `--repo`: Path to the git repository (default: current directory or auto-detected parent).
- `-v`, `--verbose`: Enable verbose logging output.

## Quality

Quality: pylint 10.00/10 · 90% coverage · 0 dependencies

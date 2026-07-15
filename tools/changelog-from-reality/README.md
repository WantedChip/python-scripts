# changelog-from-reality

Compare releases, tags, or commits and generate a factual changelog from actual code changes and AST analysis, rather than relying on commit message quality.

## Usage

```bash
python changelog_from_reality.py <from-ref> <to-ref> [options]
```

### Options

- `-r`, `--repo`: Path to target git repository (default: current directory).
- `-o`, `--output`: Path to write the generated markdown changelog file.
- `-v`, `--verbose`: Enable verbose logging output.

## Quality

Quality: pylint 10.00/10 · 90% coverage · 0 dependencies

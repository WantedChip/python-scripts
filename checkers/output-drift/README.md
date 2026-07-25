# Output Drift Checker

`output-drift` tests documentation terminal sessions and command blocks in Markdown files against actual command executions, applying volatile field normalization (timestamps, PIDs, UUIDs, addresses, file paths) to report drifted documentation outputs.

## Usage

```bash
python main.py [path] [options]
```

### Options
- `path`: Markdown file or directory path (default: `.`)
- `--update`: Automatically update out-of-date documentation code block outputs in Markdown files
- `--timeout`: Command execution timeout in seconds (default: `10`)
- `--format`: Output format (`text` or `json`, default: `text`)

### Markdown Format Supported

```markdown
```bash
$ python -c "print('hello')"
hello
```
```

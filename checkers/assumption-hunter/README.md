# Assumption Hunter

`assumption-hunter` is a static analysis tool that scans Python project source code to uncover hidden environmental assumptions (CWD dependence, hardcoded `/tmp` paths, missing explicit UTF-8 encodings, local timezone assumptions, un-sorted filename listings, shell execution assumptions, env variable indexing, external CLI dependencies, etc.).

## Usage

```bash
python main.py [path] [options]
```

### Options
- `path`: Target directory or file to scan (default: `.`)
- `--format`: Output format (`text` or `json`, default: `text`)
- `--min-severity`: Minimum severity filter (`LOW`, `MEDIUM`, `HIGH`, default: `LOW`)
- `--ignore-rule`: Skip specific rule IDs (e.g. `--ignore-rule MISSING_ENCODING`)
- `--exclude`: Exclude specific directories (e.g. `--exclude tests`)

### Example

```bash
python main.py ./src --format text --min-severity MEDIUM
```

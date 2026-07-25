# Copy Drift Checker

`copy-drift` discovers structurally similar code or configuration blocks across files/repositories, analyzes Git history co-evolution, and warns when a block has been updated while its sibling duplicate blocks were left unchanged (copy drift).

## Usage

```bash
python main.py [path] [options]
```

### Options
- `path`: Target directory or file path to analyze (default: `.`)
- `--similarity-threshold`: Similarity threshold between 0.0 and 1.0 (default: `0.75`)
- `--min-lines`: Minimum code block line length (default: `4`)
- `--format`: Output format (`text` or `json`, default: `text`)

### Example

```bash
python main.py ./src --similarity-threshold 0.70 --format text
```

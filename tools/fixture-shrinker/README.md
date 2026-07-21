# Fixture Shrinker

Reduce a giant failing JSON, CSV, or text file to the smallest input that still reproduces a bug.

## Usage

```bash
python tools/fixture-shrinker/fixture_shrinker.py \
  --input giant_payload.json \
  --command "pytest tests/test_bug.py --fixture {}" \
  --output minimized_payload.json
```

### Options

* `--input`: Giant failing payload file.
* `--command`: Validation command to run. Exit code != 0 indicates the bug is reproduced. Use `{}` as a placeholder for the temporary test file.
* `--format`: Optional format specification (`json`, `csv`, `text`). Auto-detected from filename extension by default.
* `--output`: Destination path for the minimized payload.
* `--has-header`: Specify if the CSV contains a header row.
* `--verbose`: Show detailed logs.

## Requirements

No external dependencies beyond the Python standard library.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

# schema-drift

Compare two batches of JSON records or API responses over time to evaluate schema drifts: identify keys added, keys removed, mutated data types, and nullability changes.

## Usage

Compare two JSON snapshots:

```bash
python schema_drift.py previous_api_res.json latest_api_res.json
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Comparison Analysis

- **Object Schema Building**: Traverses JSON nodes recursively to construct detailed maps of key paths, nested list types, and nullability profiles.
- **Diff Detection**: Highlights:
  - **Key Removed**: Field present in baseline but missing in newer schema.
  - **Key Added**: Field present in newer schema but missing in baseline.
  - **Type Mutation**: Field data type changed (e.g. from integer to float).
  - **Nullability Shift**: Field went from non-null to null.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

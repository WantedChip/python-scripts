# Data Type Inferencer

Analyzes CSV columns, infers actual semantic data types (`integer`, `float`, `boolean`, `datetime`, `json`, `enum`, `string`), calculates null ratios and distinct value statistics, and outputs a JSON schema profile or converted CSV.

## Features

- **Multi-Type Inference**: Detects integers, floats, booleans (`true`/`false`, `1`/`0`, `yes`/`no`), datetimes (ISO 8601, slash/dash formats), JSON structures (`{...}`, `[...]`), and categorical enums.
- **Column Analytics**: Computes null ratio, unique value counts, and sample value slices per column.
- **JSON Schema Export**: Generates rich dataset schema JSON documents.
- **Converted Output**: Exports formatted CSV with typed field values.

## Usage

```bash
python main.py -i dataset.csv -s schema.json -c converted_dataset.csv --sample-size 1000 --max-enum-cardinality 10
```

### Command Line Options

- `-i, --input-file`: (Required) Path to input CSV file.
- `-s, --schema-output`: Path to write JSON schema profile.
- `-c, --converted-output`: Path to write converted CSV output.
- `--sample-size`: Number of rows to sample for inference (0 for all rows). Default: `0`.
- `--max-enum-cardinality`: Maximum unique values threshold for enum type detection. Default: `10`.

## Running Unit Tests

```bash
python -m unittest discover -s tests
```

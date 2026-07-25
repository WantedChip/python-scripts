# CSV Column Reorder

A utility tool to reorder, select, drop, or inspect columns in CSV files based on header sequences or JSON configuration files. Handles missing optional columns with defaults.

## Features

- **Header Inspection**: Print indexed header column names of any CSV file.
- **Reordering & Selection**: Define target header ordering and drop unlisted fields.
- **Keep Extra Columns**: Option to append extra non-selected columns at the end.
- **Default Fallbacks**: Column-specific default values or global fallback for missing fields.
- **Config file support**: Specify column sequence and defaults in a JSON file.

## Usage

### Inspect CSV Headers
```bash
python main.py --input data.csv --inspect
```

### Reorder Columns via CLI
```bash
python main.py --input data.csv --columns "id,last_name,first_name,email" --output output.csv
```

### Reorder via JSON Configuration
```bash
python main.py --input data.csv --config reorder_config.json --output output.csv
```

#### Sample `reorder_config.json`:
```json
{
  "order": ["id", "username", "email", "status"],
  "defaults": {
    "status": "Active"
  }
}
```

### Run Unit Tests
```bash
python -m unittest discover -s tests
```

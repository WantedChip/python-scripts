# JSON Flatten Nested Tool

A Python script to recursively flatten deeply nested JSON structures, objects, and arrays into single-level key-value dictionaries (e.g. `user.address.city`, `items.0.name`) and export them to CSV or JSON.

## Features

- **Recursive Flattener**: Flattens arbitrary nested dicts and arrays.
- **Array Index Keying**: Maps array items to indexed keys (`items.0.id`, `items.1.id`).
- **Separator Customization**: Choose custom delimiters (`.`, `_`, `/`, etc.).
- **CSV & JSON Export**: Export flattened data straight into CSV files or formatted JSON.
- **Max Depth Limit**: Limit recursion depth for partial flattening.

## Usage

### Flatten JSON to CSV
```bash
python main.py --input nested_data.json --output flat_data.csv --format csv
```

### Flatten JSON with Custom Separator
```bash
python main.py --input nested_data.json --sep "_" --format json
```

### Disable Array Flattening
```bash
python main.py --input nested_data.json --no-array-flatten --format csv
```

### Run Unit Tests
```bash
python -m unittest discover -s tests
```

# Date Format Standardizer

A python tool for detecting inconsistent date/time strings in CSV columns (e.g., `"MM/DD/YYYY"`, `"DD-MM-YYYY"`, `"Jan 5 2024"`, Unix timestamps) and standardizing them into ISO 8601 format (`YYYY-MM-DD`).

## Features

- **Multi-Format Date Parser**: Handles ISO, slashes, dashes, spelled-out month names, ordinal suffixes (`1st`, `2nd`), and Unix timestamps.
- **Target Specific Columns**: Convert one or multiple date/time headers in CSV files.
- **Ambiguity Handling**: Toggle `--day-first` for DD/MM/YYYY vs MM/DD/YYYY regional formatting.
- **Timezone Normalization**: Convert offset datetime strings into UTC ISO standard.
- **Flexible Fallbacks**: Choose fallback strategy for unparseable entries (`keep`, `null`, `custom`).

## Usage

### Basic Date Standardization
```bash
python main.py --input raw_data.csv --columns "created_at,dob" --output clean_data.csv
```

### Day-First Regional Priority (DD/MM/YYYY)
```bash
python main.py --input uk_data.csv --columns "order_date" --day-first --output output.csv
```

### Custom Fallback for Failed Parses
```bash
python main.py --input dates.csv --columns "event_date" --fallback custom --custom-fallback "1970-01-01" --output normalized.csv
```

### Run Unit Tests
```bash
python -m unittest discover -s tests
```

# Config Migration Tool

A CLI utility to safely convert configuration files (JSON/YAML/TOML) from older schema formats to new versions. Features include timestamped backup generation, declarative schema routing, custom Python procedural logic execution, and JSON Schema validation checks.

## Features

- **Multi-Format Parsing**: Reads JSON, YAML, and TOML (TOML requires Python 3.11+ `tomllib`) configurations and writes JSON and YAML outputs.
- **Safety Backups**: Creates timestamped file copies (e.g. `config.yaml.bak_YYYYMMDD_HHMMSS`) before executing any modification.
- **Declarative Migration Actions**:
  - `rename`: Rename simple keys.
  - `move`: Relocate config items to new path structures using dot-notation.
  - `transform`: Map data types or convert values (int, float, str, bool, lower, upper, split, join).
  - `set_default`: Set default values on missing parameters.
  - `delete`: Safely remove keys or nested keys.
- **Custom Migrations**: Extensible via custom Python scripts implementing procedural changes.
- **Migration Pathway Engine**: Finds the shortest pathway DAG of migration rules between start and target version nodes.
- **Schema Validation & Reports**: Integrates with `jsonschema` to validate migrated configurations and outputs JSON summary reports.

## Usage

```bash
# Run declarative migration rules to version 2.0
python config_migration.py -i config.json -r rules.json -t 2.0 --report report.json

# Migrate using a custom Python script override
python config_migration.py -i config.yaml -c migrate_custom.py

# Migrate and validate the output configuration against a target JSON Schema
python config_migration.py -i config.json -r rules.json -t 3.0 -s schema.json
```

## Requirements

- Python 3.x
- `PyYAML` (optional, for YAML support)
- `jsonschema` (optional, for validation support)

Quality: pylint 10.00/10 · 81% coverage · 2 dependencies

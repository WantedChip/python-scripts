# JSON/YAML Config Validator

Validate JSON and YAML configuration files against a JSON Schema, producing highly readable error reports with exact line/column indicators and source code context.

## Usage

```bash
# General usage
python config_validator.py --schema <path_to_schema> <path_to_config> [<additional_configs>...]

# Fail fast on the first validation error
python config_validator.py --schema schema.json config.yaml --fail-fast

# Disable ANSI color encoding in the output
python config_validator.py --schema schema.json config.yaml --no-color
```

### Example

Assuming a schema `schema.json`:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "port": { "type": "integer", "minimum": 1024 }
  },
  "required": ["port"]
}
```

And an invalid configuration `config.yaml`:
```yaml
port: 80
host: localhost
```

Running the validation:
```bash
python config_validator.py --schema schema.json config.yaml
```

Will output:
```
Validation Error [minimum]: 80 is less than the minimum of 1024
  --> config.yaml:1:7
    |
  1 | port: 80
    |       ^ 80 is less than the minimum of 1024
  2 | host: localhost
    |
```

## Requirements

- `jsonschema==4.23.0`
- `PyYAML==6.0.1`

Install dependencies using:
```bash
pip install -r requirements.txt
```

## Notes

- Supports standard JSON Schema validation drafts supported by the `jsonschema` library.
- Safely reports duplicate keys in both JSON structures and YAML mappings.
- Syntax errors in configuration files are formatted with the same beautiful compiler-like snippets.

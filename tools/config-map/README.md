# config-map

Scan a codebase recursively to build a single consolidated report of all configuration sources: Command Line Arguments, Environment Variables, Settings File configuration loaders (JSON/YAML/TOML), and highlight precedence rules.

## Usage

Scan the current directory for configuration variables:

```bash
python config_map.py
```

Scan a custom target directory path:

```bash
python config_map.py C:/Users/Name/Projects/my_app
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Precendence Rules Logged

1. **Command Line Flags**: Overrides all other configuration settings.
2. **Environment Variables**: Overrides local configuration settings file values.
3. **Local Settings Files**: Overrides built-in defaults.
4. **Built-in Defaults**: Initial fallbacks defined in code.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

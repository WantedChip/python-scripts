# Config Experiment Tool

`config-experiment` runs a base command against several configuration file variations, capturing execution results (exit code, stdout, stderr, execution time) and generating a matrix difference report to highlight which configuration settings actually changed runtime behavior.

## Usage

```bash
python main.py --command "python app.py --config {config}" --configs config1.json config2.json --format markdown --output report.md
```

## Options

- `--command`: Base command template. Supports `{config}` placeholder or environment variable injection.
- `--configs`: List of paths to configuration files.
- `--env-var`: Environment variable name to inject config path into (default: `CONFIG_FILE`).
- `--format`: Output report format (`text`, `markdown`, `json`).
- `--output`: File path to save report to (stdout if omitted).
- `--timeout`: Maximum duration in seconds per run (default: 30.0).

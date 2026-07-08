# Log Analyzer

Parse huge log files, group repeated errors, detect spikes, and summarize the most important failures.

## Usage

```bash
python log_analyzer.py <path_to_log_file> [options]
```

### Examples

```bash
# Analyze a log file using auto-detected format
python log_analyzer.py my_app.log

# Analyze a log file and output JSON
python log_analyzer.py my_app.log --json-output

# Use a specific predefined format (common, combined, python, log4j)
python log_analyzer.py access.log -t combined

# Specify a custom regex and timestamp format
python log_analyzer.py custom.log -p "^\[([^\]]+)\] (\S+) - (.*)$" --ts-group 1 --level-group 2 --msg-group 3 --ts-format "%d/%b/%Y:%H:%M:%S"
```

### Options

* `-t, --type`: Predefined log format (`common`, `combined`, `python`, `log4j`).
* `-p, --pattern`: Custom regex pattern to match log lines.
* `--ts-group`: Group index (1-based) of timestamp in the custom regex pattern.
* `--level-group`: Group index (1-based) of log level in the custom regex pattern.
* `--msg-group`: Group index (1-based) of message in the custom regex pattern.
* `--ts-format`: The strftime format for parsing the timestamp (e.g. `%%Y-%%m-%%d %%H:%%M:%%S`).
* `-w, --window`: The bucket window size in minutes for spike detection (default: 5).
* `-s, --spike-threshold`: The number of standard deviations above the mean to trigger a spike alert (default: 2.0).
* `-j, --json-output`: Print output as JSON.
* `-v, --verbose`: Enable debug logging.

## Requirements

None. This script runs entirely on Python's standard library.

## Notes

* Message grouping automatically normalizes hexadecimal addresses, UUIDs, IPv4/IPv6 addresses, quotes, and numbers into general placeholders (like `<HEX>`, `<UUID>`, `<IP>`, `<STR>`, `<NUM>`) to collapse repeated errors that only differ by parameters.
* This script reads logs line-by-line using generators, making it highly memory efficient even for files containing millions of entries.

# Swallow Trace Tool

Trace Python script execution to detect swallowed or suppressed exceptions and analyze downstream causal impacts (such as fallback return values).

## Features
- Dynamic runtime execution tracing using `sys.settrace`.
- Tracks raised exceptions and matches them against function return points.
- Highlights swallowed exceptions where an error was caught and a fallback value (`None`, `False`, `0`, `""`) was returned.
- Helps identify root causes for silent failures or false symptom locations.

## Usage

```bash
python main.py /path/to/target_script.py [script_arguments...]
```

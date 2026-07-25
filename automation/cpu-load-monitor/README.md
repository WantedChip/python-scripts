# CPU Load Monitor

A Python utility that monitors overall CPU load and per-core utilization over intervals, producing summary reports with peak usage times.

## Features

- Samples overall CPU percentage and individual core metrics
- Calculates average and peak utilization across sampling duration
- Tracks exact timestamp of peak load
- Generates clean console tables and optional JSON reports

## Usage

```bash
python main.py
python main.py --count 10 --interval 2.0
python main.py --count 5 --output-json cpu_report.json
```

## Running Tests

```bash
python -m unittest discover -s tests
```

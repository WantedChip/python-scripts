# Memory Usage Monitor

A Python utility that monitors RAM and Swap memory utilization over time and logs periodic statistics to a CSV file.

## Features

- Samples physical RAM (Total, Used, Free, %)
- Samples Swap space (Total, Used, Free, %)
- Real-time terminal output during execution
- Writes records continuously to CSV file

## Usage

```bash
python main.py
python main.py --interval 1.0 --output system_mem.csv
python main.py --count 10 --interval 5.0
```

## Running Tests

```bash
python -m unittest discover -s tests
```

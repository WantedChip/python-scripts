# File Size Visualizer CLI

A command-line tool that scans filesystem directory trees to generate ASCII tree structures and treemap-style disk usage summaries complete with relative percentage bar charts.

## Features

- **Recursive Disk Usage Calculation**: Calculates cumulative disk usage of folders and files.
- **Configurable Traversal Depth**: Control inspection depth (`--depth`) to limit visual noise on large file systems.
- **Human-Readable Sizes**: Displays byte metrics automatically formatted as `B`, `KB`, `MB`, `GB`, `TB`.
- **ASCII Visual Bar Charts**: Interactive visual progress bars showing child percentage contribution relative to parent directory size.
- **Top N Heavy Items Treemap**: Breakdown listing the top N largest files and subdirectories.

## Usage

```bash
python main.py --dir /path/to/folder --depth 3 --top 10
```

### CLI Command Options

| Option | Short | Description | Default |
|---|---|---|---|
| `--dir` | `-d` | Root directory to analyze | `.` |
| `--depth` | | Maximum directory traversal depth | `2` |
| `--top` | | Number of top heavy items to display | `10` |
| `--bar-width` | | Width of ASCII visual bar | `18` |
| `--style` | | Visualization mode (`tree`, `treemap`, `all`) | `all` |

## Output Example

```
=== Disk Usage ASCII Tree ===
project/ [████████████████████] 100.0% (   5.20 MB)
├── node_modules/ [██████████████████░░]  90.4% (   4.70 MB)
├── dist/ [██░░░░░░░░░░░░░░░░░░]   7.7% ( 400.00 KB)
└── src/ [░░░░░░░░░░░░░░░░░░░░]   1.9% ( 100.00 KB)

=== Top 10 Heaviest Files / Folders ===
Type   | Disk Size  | Usage %                        | Path
--------------------------------------------------------------------------------
DIR    |    4.70 MB | [██████████████████████░░░] 90.4% | node_modules
DIR    |  400.00 KB | [██░░░░░░░░░░░░░░░░░░░░░░░]  7.7% | dist
DIR    |  100.00 KB | [░░░░░░░░░░░░░░░░░░░░░░░░░]  1.9% | src
```

## Running Unit Tests

```bash
python -m unittest discover tests
```

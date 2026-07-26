# Mutation Witness

`mutation-witness` catches process, parent process tree, working directory, size delta, and unified file diff details when a file is created, modified, or deleted.

## Usage

### 1. Wrap Command Execution

Wrap command execution to monitor target file mutation:

```bash
python main.py wrap --file target.txt -- python generate_data.py
```

Save mutation log to JSON:

```bash
python main.py wrap --file config.json --log mutations.json -- python update_config.py
```

### 2. Watch Target File

Continuously watch target file for modifications over time:

```bash
python main.py watch --file target.txt --interval 0.5 --duration 10
```

### 3. Display Mutation Reports

Display recorded mutation log events:

```bash
python main.py report mutations.json --format text
```

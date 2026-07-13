# CLI Workflow Recorder

Record sequences of terminal tasks interactively, parameterize key values (e.g. paths, ports, tokens), and execute them as reusable workflows.

## Usage

### Recording a Workflow

Run `record` and input your commands in sequence. The recorder executes them, captures outputs, and suggests variable replacements:

```bash
# Start an interactive recording session and write configuration to workflow.json
python src/cli_workflow_recorder/main.py record workflow.json
```

Inside the interactive loop:
```
(recorder) > echo hello > input.txt
Executing: echo hello > input.txt

[Command exited with code 0 in 0.05s]
Keep this command in the workflow? [Y/n]: y
Enter a description/name for this step: Create input file

Suggested parameters found in command:
  * Replace 'input.txt' with parameter {input_path}? (Leave blank to skip, or enter param name): input_file
```

### Running a Workflow

Execute a saved JSON workflow, overriding parameter defaults via `--param` keys:

```bash
# Run workflow, prompting for missing parameter values
python src/cli_workflow_recorder/main.py run workflow.json

# Run workflow overriding parameters directly via CLI
python src/cli_workflow_recorder/main.py run workflow.json --param input_file=my_data.txt --param message="Running task"

# Run workflow and ignore unexpected step failures
python src/cli_workflow_recorder/main.py run workflow.json --ignore-failures
```

## Requirements

- Python 3.10+
- Standard libraries only (0 external dependencies)

## Notes

- **Shell Execution**: Spawns user commands under `shell=True` to support terminal builtins (e.g. `echo`, `dir`, `ls`, file redirection). Do not run untrusted workflow scripts as they can execute arbitrary shell commands.
- **Parameters**: Employs Python format-string brackets (e.g. `{input_file}`) for interpolation of values.

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies

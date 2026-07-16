#!/usr/bin/env python3
"""CI Local — Read a CI workflow and generate local commands/scripts to reproduce it.

Parses GitHub Actions YAML files, identifies jobs, expands matrix parameters,
maps standard steps to local commands, and exports an executable script.
"""

import argparse
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import yaml  # type: ignore[import-untyped]

# Standard GitHub actions mapping to local commands or notes
STANDARD_ACTIONS = {
    r"actions/checkout@.*": {
        "status": "MAPPED",
        "description": "Checkout code",
        "commands": ["git status"],
        "note": "Verify the local repository is checked out and clean.",
    },
    r"actions/setup-python@.*": {
        "status": "MAPPED",
        "description": "Set up Python environment",
        "commands": ["python --version"],
        "note": "Ensure your active virtual environment matches the target version.",
    },
    r"actions/cache@.*": {
        "status": "SKIPPED",
        "description": "Cache dependencies",
        "commands": [],
        "note": (
            "Caching is handled natively by local package " "managers (pip, npm, etc.)."
        ),
    },
}


def parse_workflow(filepath: str) -> Dict[str, Any]:
    """Parse the YAML CI workflow file.

    Args:
        filepath: Path to the workflow file.

    Returns:
        The parsed workflow configuration.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If parsing fails.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Workflow file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as file:
        content = yaml.safe_load(file)
        if not isinstance(content, dict):
            raise ValueError("Invalid workflow: Root must be a dictionary.")
        return content


def get_jobs(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve jobs from the workflow dictionary.

    Args:
        workflow: The parsed workflow dictionary.

    Returns:
        A dictionary mapping job IDs to job configurations.
    """
    jobs = workflow.get("jobs", {})
    if isinstance(jobs, dict):
        return jobs
    return {}


def expand_matrix(matrix_config: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """Expand matrix combinations from a job strategy matrix.

    Args:
        matrix_config: The matrix configuration mapping variable names to lists.

    Returns:
        A list of dictionaries, each representing a single matrix combination.
    """
    if not matrix_config or not isinstance(matrix_config, dict):
        return [{}]

    keys = sorted(matrix_config.keys())
    combinations: List[Dict[str, Any]] = [{}]

    for key in keys:
        values = matrix_config[key]
        if not isinstance(values, list):
            values = [values]
        new_combinations = []
        for combo in combinations:
            for val in values:
                new_combo = combo.copy()
                new_combo[key] = val
                new_combinations.append(new_combo)
        combinations = new_combinations

    return combinations


def resolve_expression(text: str, matrix_vars: Dict[str, Any]) -> str:
    """Resolve basic GitHub Actions expressions like ${{ matrix.variable }} in text.

    Args:
        text: The string containing GHA expressions.
        matrix_vars: Active matrix values.

    Returns:
        The resolved string.
    """
    if not isinstance(text, str):
        return text

    # Handle ${{ matrix.var }} expressions
    def replace_matrix(match: re.Match[str]) -> str:
        expression = match.group(1).strip()
        # Look for matrix.var pattern
        parts = expression.split(".")
        if len(parts) >= 2 and parts[0] == "matrix":
            var_name = parts[1]
            return str(matrix_vars.get(var_name, f"{{{var_name}}}"))
        # Fallback to keep the expression or format it as env variable
        return f"${{{expression}}}"

    pattern = r"\$\{\{\s*([^}]+)\s*\}\}"
    return re.sub(pattern, replace_matrix, text)


def analyze_step(
    step: Dict[str, Any], matrix_vars: Dict[str, Any]
) -> Tuple[str, str, List[str], str]:
    """Analyze a single workflow step and determine its local reproduction logic.

    Args:
        step: The GHA step configuration dictionary.
        matrix_vars: Active matrix variables.

    Returns:
        A tuple of (status, description, list of local commands, notes).
    """
    name = step.get("name", step.get("id", "Unnamed Step"))
    resolved_name = resolve_expression(name, matrix_vars)

    # 1. Run Step (shell script execution)
    if "run" in step:
        run_cmd = step["run"]
        resolved_cmd = resolve_expression(run_cmd, matrix_vars)
        commands = [line.strip() for line in resolved_cmd.split("\n") if line.strip()]
        return "REPRODUCIBLE", resolved_name, commands, "Runs shell command."

    # 2. Uses Step (action execution)
    if "uses" in step:
        action_name = step["uses"]
        for action_pattern, mapping in STANDARD_ACTIONS.items():
            if re.match(action_pattern, action_name):
                return (
                    str(mapping["status"]),
                    resolved_name,
                    list(mapping["commands"]),
                    str(mapping["note"]),
                )
        return (
            "WARNING",
            resolved_name,
            [],
            f"Third-party action '{action_name}' cannot run locally directly.",
        )

    return "SKIPPED", resolved_name, [], "Unknown step type."


def generate_local_script(
    job_id: str,
    steps_analysis: List[Tuple[str, str, List[str], str]],
    shell_type: str = "bash",
) -> str:
    """Generate shell script content containing the local commands.

    Args:
        job_id: The identifier of the job.
        steps_analysis: List of analyzed step details.
        shell_type: 'bash' or 'powershell'.

    Returns:
        The generated script content.
    """
    lines: List[str] = []
    if shell_type == "powershell":
        lines.append("#!/usr/bin/env pwsh")
        lines.append(f"# Local reproduction of job: {job_id}")
        lines.append("$ErrorActionPreference = 'Stop'\n")
    else:
        lines.append("#!/usr/bin/env bash")
        lines.append(f"# Local reproduction of job: {job_id}")
        lines.append("set -euo pipefail\n")

    for status, name, commands, note in steps_analysis:
        lines.append(f"# --- Step: {name} ({status}) ---")
        if note:
            lines.append(f"# Note: {note}")
        if status in ("REPRODUCIBLE", "MAPPED") and commands:
            for cmd in commands:
                lines.append(cmd)
        else:
            lines.append(f"# Skipped: {name}")
        lines.append("")

    return "\n".join(lines)


# pylint: disable=too-many-locals,too-many-branches
def process_workflow_local(
    filepath: str,
    job_name: Optional[str] = None,
    matrix_selection: Optional[str] = None,
) -> int:
    """Process workflow, print audit information, and output script.

    Args:
        filepath: Path to workflow YAML.
        job_name: Job to reproduce.
        matrix_selection: Matrix overrides (e.g. "os=ubuntu-latest,py-version=3.12").

    Returns:
        Status code (0 for success).
    """
    try:
        wf = parse_workflow(filepath)
    except Exception as err:  # pylint: disable=broad-except
        print(f"Error parsing workflow: {err}", file=sys.stderr)
        return 1

    jobs = get_jobs(wf)
    if not jobs:
        print("No jobs found in workflow.", file=sys.stderr)
        return 1

    # If no job name specified, list jobs and let user know
    if not job_name:
        print("Available jobs in workflow:")
        for j_id in jobs:
            print(f"  - {j_id}")
        print("\nPlease specify a job name with --job <job_name>")
        return 0

    if job_name not in jobs:
        print(f"Job '{job_name}' not found. Available jobs:", file=sys.stderr)
        for j_id in jobs:
            print(f"  - {j_id}", file=sys.stderr)
        return 1

    job = jobs[job_name]
    matrix_config = job.get("strategy", {}).get("matrix", {})
    combinations = expand_matrix(matrix_config)

    selected_matrix = combinations[0]  # Default to first combination
    if matrix_selection and combinations != [{}]:
        overrides = {}
        for part in matrix_selection.split(","):
            if "=" in part:
                k, val = part.split("=", 1)
                overrides[k.strip()] = val.strip()
        selected_matrix = combinations[0].copy()
        selected_matrix.update(overrides)

    print(f"Reproducing job: {job_name}")
    if selected_matrix:
        print(f"Active matrix parameters: {selected_matrix}")

    steps = job.get("steps", [])
    steps_analysis = []
    print("\nStep Analysis:")
    print("-" * 80)
    for idx, step in enumerate(steps, 1):
        status, name, cmds, note = analyze_step(step, selected_matrix)
        steps_analysis.append((status, name, cmds, note))
        print(f"[{idx:02d}] {name}")
        print(f"     Status: {status}")
        print(f"     Note:   {note}")
        if cmds:
            print("     Local Commands:")
            for cmd in cmds:
                print(f"       $ {cmd}")
        print("-" * 80)

    # Determine default script name and write
    shell_type = "powershell" if os.name == "nt" else "bash"
    ext = "ps1" if shell_type == "powershell" else "sh"
    script_name = f"reproduce_{job_name}.{ext}"

    script_content = generate_local_script(job_name, steps_analysis, shell_type)
    with open(script_name, "w", encoding="utf-8") as f:
        f.write(script_content)

    print(f"\nGenerated local reproduction script: {script_name}")
    print(
        "Review this script before running, as some manual setups/env vars "
        "may be needed."
    )
    return 0


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="ci-local: Translate GHA CI steps to local commands."
    )
    parser.add_argument(
        "--workflow",
        default=".github/workflows/ci.yml",
        help="Path to the GHA workflow file",
    )
    parser.add_argument("--job", help="Job name to parse and reproduce")
    parser.add_argument(
        "--matrix",
        help=(
            "Matrix values to use, comma-separated "
            "(e.g. os=ubuntu-latest,python-version=3.12)"
        ),
    )

    args = parser.parse_args()
    sys.exit(process_workflow_local(args.workflow, args.job, args.matrix))


if __name__ == "__main__":
    main()

# pylint: disable=duplicate-code
"""CLI Workflow Recorder — record and execute parameterized terminal tasks."""

import argparse
import json
import logging
import re
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("cli_workflow_recorder")

# Regex to detect potential path parameter values (e.g. text.txt, /some/dir)
PATH_VALUE_RE = re.compile(r"\b[a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]{2,5}\b")

# Regex to detect standalone numeric parameter values (like ports 8080)
PORT_VALUE_RE = re.compile(r"\b\d{2,5}\b")


def suggest_parameters(cmd_str: str) -> Dict[str, str]:
    """Inspect a command string and suggest parameters to extract.

    Args:
        cmd_str: The raw command line string.

    Returns:
        A dictionary mapping the detected literal value to suggested parameter name.
    """
    suggestions: Dict[str, str] = {}

    # Find file/path matches
    for match in PATH_VALUE_RE.finditer(cmd_str):
        val = match.group(0)
        # Avoid matching python command itself
        if val in ["python", "python3", "pip"]:
            continue
        # Deduce a variable name
        name_parts = Path(val).stem.replace(".", "_").replace("-", "_")
        param_name = f"{name_parts}_path" if name_parts else "file_path"
        # Sanitize param name
        param_name = re.sub(r"\W+", "", param_name)
        suggestions[val] = param_name

    # Find numbers
    for match in PORT_VALUE_RE.finditer(cmd_str):
        val = match.group(0)
        suggestions[val] = "port_num"

    return suggestions


def _process_suggestions(cmd: str, parameters: Dict[str, str]) -> str:
    """Helper to interactively prompt for parameter replacement suggestions."""
    suggestions = suggest_parameters(cmd)
    final_cmd = cmd
    if not suggestions:
        return final_cmd

    print("\nSuggested parameters found in command:")
    for val, param in suggestions.items():
        prompt_text = (
            f"  * Replace '{val}' with parameter {{{param}}}? "
            "(Leave blank to skip, or enter param name): "
        )
        ans = input(prompt_text).strip()
        if ans != "":
            # If they typed something else, use it
            param_name = ans
        elif ans == "" and len(ans) == 0:
            # If they just hit enter, use suggested param
            param_name = param
        else:
            # Skip
            continue

        # Record parameter and replace in command
        parameters[param_name] = val
        final_cmd = final_cmd.replace(val, f"{{{param_name}}}")

    return final_cmd


def record_workflow(output_path: Path) -> None:
    """Run the interactive workflow recording session.

    Args:
        output_path: Path to write the final JSON workflow configuration.
    """
    print("=" * 60)
    print("            CLI WORKFLOW RECORDER (RECORD MODE)            ")
    print("=" * 60)
    print("Type commands as you would in your normal shell.")
    print("Type 'exit' or 'stop' to finish recording and save the workflow.\n")

    workflow_name = input("Enter a name for this workflow [My Workflow]: ").strip()
    if not workflow_name:
        workflow_name = "My Workflow"

    steps: List[Dict[str, Any]] = []
    parameters: Dict[str, str] = {}

    while True:
        try:
            cmd = input("\n(recorder) > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)

        if not cmd:
            continue

        if cmd.lower() in ["exit", "stop"]:
            break

        # Run command and capture status
        print(f"Executing: {cmd}")
        start_time = time.time()
        res = subprocess.run(  # nosec B602
            cmd, shell=True, capture_output=True, text=True, check=False
        )
        duration = time.time() - start_time

        # Print outputs
        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)

        print(f"\n[Command exited with code {res.returncode} in {duration:.2f}s]")

        keep = input("Keep this command in the workflow? [Y/n]: ").strip().lower()
        if keep in ["n", "no"]:
            continue

        step_name = input("Enter a description/name for this step: ").strip()
        if not step_name:
            step_name = f"Run '{cmd[:20]}'"

        # Parameter suggestion loop
        final_cmd = _process_suggestions(cmd, parameters)

        steps.append(
            {
                "name": step_name,
                "command": final_cmd,
                "expected_exit_code": res.returncode,
            }
        )

    # Save to file
    workflow = {
        "name": workflow_name,
        "parameters": parameters,
        "steps": steps,
    }

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(workflow, f, indent=2, ensure_ascii=False)
        print(f"\nWorkflow successfully saved to {output_path}!")
    except OSError as e:
        logger.error("Failed to save workflow JSON file: %s", e)
        sys.exit(1)


def _run_step(
    step_info: Dict[str, Any],
    cmd: str,
    ignore_failures: bool,
) -> bool:
    """Execute a single workflow step command.

    Returns:
        True if step succeeded or failure was ignored, False if workflow should abort.
    """
    print(f"\n[{step_info['idx']}/{step_info['total']}] {step_info['name']}")
    print(f"Executing: {cmd}")

    res = subprocess.run(
        cmd, shell=True, capture_output=False, check=False
    )  # nosec B602

    expected = step_info["expected"]
    if res.returncode != expected:
        if not ignore_failures:
            logger.error(
                "Step '%s' failed (Exit code: %d, Expected: %d). "
                + "Aborting workflow.",
                step_info["name"],
                res.returncode,
                expected,
            )
            return False

        logger.warning(
            "Step '%s' failed (Exit code: %d, Expected: %d). "
            "Continuing (ignore-failures active).",
            step_info["name"],
            res.returncode,
            expected,
        )
    return True


def _parse_cli_params(param_args: List[str]) -> Dict[str, str]:
    """Parse key=value parameters from CLI arguments."""
    cli_params: Dict[str, str] = {}
    for p in param_args:
        if "=" in p:
            k, v = p.split("=", 1)
            cli_params[k.strip()] = v.strip()
    return cli_params


def _resolve_params(
    wf_params: Dict[str, str], cli_params: Dict[str, str]
) -> Dict[str, str]:
    """Interactively resolve values for required workflow parameters."""
    params: Dict[str, str] = {}
    for name, default_val in wf_params.items():
        if name in cli_params:
            params[name] = cli_params[name]
        else:
            try:
                prompt_text = (
                    f"Enter value for parameter '{name}' " f"[default: {default_val}]: "
                )
                user_val = input(prompt_text).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                sys.exit(1)
            params[name] = user_val if user_val else default_val
    return params


def run_workflow(
    workflow_path: Path, param_args: List[str], ignore_failures: bool
) -> None:
    """Run a parameterized workflow from a JSON config file.

    Args:
        workflow_path: Path to the workflow JSON file.
        param_args: Command line parameters formatted as 'name=value'.
        ignore_failures: Continue running next steps even if a command fails.
    """
    if not workflow_path.is_file():
        logger.error("Workflow file not found: %s", workflow_path)
        sys.exit(1)

    try:
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to parse workflow file: %s", e)
        sys.exit(1)

    print("=" * 60)
    wf_name = workflow.get("name", "Unnamed")
    print(f"            RUNNING WORKFLOW: {wf_name}            ")
    print("=" * 60)

    cli_params = _parse_cli_params(param_args)
    params = _resolve_params(workflow.get("parameters", {}), cli_params)

    # Run steps
    steps = workflow.get("steps", [])
    if not steps:
        print("No steps found in workflow.")
        return

    for idx, step in enumerate(steps, 1):
        try:
            cmd = step.get("command", "").format(**params)
        except KeyError as e:
            logger.error(
                "Missing parameter value for step '%s': %s",
                step.get("name", f"Step {idx}"),
                e,
            )
            sys.exit(1)

        success = _run_step(
            {
                "idx": idx,
                "total": len(steps),
                "name": step.get("name", f"Step {idx}"),
                "expected": step.get("expected_exit_code", 0),
            },
            cmd,
            ignore_failures,
        )
        if not success:
            sys.exit(1)

    print("\n" + "=" * 60)
    print("            WORKFLOW COMPLETED SUCCESSFULLY!            ")
    print("=" * 60)


def main() -> None:
    """CLI execution entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "CLI Workflow Recorder — record sequences of "
            "terminal tasks and run them parameterized."
        )
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Subcommand to execute."
    )

    # record subcommand
    record_parser = subparsers.add_parser(
        "record", help="Record a new workflow session."
    )
    record_parser.add_argument(
        "output_path",
        type=str,
        help="Path to write the workflow JSON configuration file.",
    )

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Run a recorded workflow.")
    run_parser.add_argument(
        "workflow_path",
        type=str,
        help="Path to the workflow JSON configuration file.",
    )
    run_parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Provide parameter values as name=value flags.",
    )
    run_parser.add_argument(
        "--ignore-failures",
        action="store_true",
        help=(
            "Continue execution if individual steps " "return unexpected exit codes."
        ),
    )

    args = parser.parse_args()

    if args.command == "record":
        record_workflow(Path(args.output_path))
    elif args.command == "run":
        run_workflow(Path(args.workflow_path), args.param, args.ignore_failures)


if __name__ == "__main__":
    main()

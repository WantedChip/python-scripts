"""Config Experiment Tool.

Runs a base command against multiple configuration variations, capturing
stdout, stderr, exit codes, and output artifacts, and generates a comparative
matrix difference report to highlight behavioral changes.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import difflib
import json
import os
import subprocess  # nosec B404
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunResult:
    """Class representing the result of a single experiment run."""

    config_name: str
    config_content: str
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    output_files: Dict[str, str] = field(default_factory=dict)


def run_single_config(
    command_template: str,
    config_path: Path,
    env_var_name: str = "CONFIG_FILE",
    timeout: float = 30.0,
) -> RunResult:
    """Execute a single configuration experiment in an isolated environment."""
    config_name = config_path.name
    config_content = (
        config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    )

    env = os.environ.copy()
    env[env_var_name] = str(config_path.resolve())

    if "{config}" in command_template:
        cmd = command_template.format(config=str(config_path.resolve()))
    else:
        cmd = command_template

    start_time = time.time()
    try:
        proc = subprocess.run(  # nosec B602 B603
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as e:
        exit_code = -1
        stdout = e.stdout or "" if isinstance(e.stdout, str) else ""
        stderr = f"Execution timed out after {timeout} seconds."
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        exit_code = -1
        stdout = ""
        stderr = f"Execution failed: {str(e)}"

    duration = time.time() - start_time

    return RunResult(
        config_name=config_name,
        config_content=config_content,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_sec=round(duration, 4),
    )


def compare_results(results: List[RunResult]) -> Dict[str, Any]:
    """Generate a comparative analysis matrix of experiment results."""
    if not results:
        return {"runs": [], "differences": {}}

    baseline = results[0]
    differences: Dict[str, Any] = {
        "baseline_config": baseline.config_name,
        "runs_summary": [],
        "variations": [],
    }

    for res in results:
        differences["runs_summary"].append(
            {
                "config_name": res.config_name,
                "exit_code": res.exit_code,
                "duration_sec": res.duration_sec,
                "matches_baseline": (
                    res.exit_code == baseline.exit_code
                    and res.stdout == baseline.stdout
                    and res.stderr == baseline.stderr
                ),
            }
        )

        if res.config_name == baseline.config_name:
            continue

        stdout_diff = list(
            difflib.unified_diff(
                baseline.stdout.splitlines(keepends=True),
                res.stdout.splitlines(keepends=True),
                fromfile=f"baseline ({baseline.config_name})",
                tofile=res.config_name,
            )
        )

        stderr_diff = list(
            difflib.unified_diff(
                baseline.stderr.splitlines(keepends=True),
                res.stderr.splitlines(keepends=True),
                fromfile=f"baseline ({baseline.config_name})",
                tofile=res.config_name,
            )
        )

        differences["variations"].append(
            {
                "config_name": res.config_name,
                "exit_code_diff": {
                    "baseline": baseline.exit_code,
                    "current": res.exit_code,
                    "changed": baseline.exit_code != res.exit_code,
                },
                "stdout_diff": "".join(stdout_diff),
                "stderr_diff": "".join(stderr_diff),
            }
        )

    return differences


def generate_report(comparison: Dict[str, Any], fmt: str = "text") -> str:
    """Format the comparison matrix into text, JSON, or Markdown format."""
    if fmt == "json":
        return json.dumps(comparison, indent=2)

    lines = []
    if fmt == "markdown":
        lines.append("# Configuration Experiment Difference Report")
        base_cfg = comparison.get("baseline_config")
        lines.append(f"**Baseline Configuration:** `{base_cfg}`\n")
        lines.append("## Summary")
        header_row = "| Config Name | Exit Code | Duration (s) | Matches Baseline |"
        lines.append(header_row)
        lines.append("| --- | --- | --- | --- |")
        for summary in comparison.get("runs_summary", []):
            matches = "Yes" if summary["matches_baseline"] else "**NO**"
            c_name = summary["config_name"]
            c_code = summary["exit_code"]
            c_dur = summary["duration_sec"]
            row_str = f"| `{c_name}` | {c_code} | {c_dur} | {matches} |"
            lines.append(row_str)

        lines.append("\n## Behavioral Variations")
        for var in comparison.get("variations", []):
            lines.append(f"### Configuration: `{var['config_name']}`")
            ec_diff = var["exit_code_diff"]
            if ec_diff["changed"]:
                msg = (
                    f"- **Exit Code Changed:** {ec_diff['baseline']} -> "
                    f"{ec_diff['current']}"
                )
                lines.append(msg)
            else:
                lines.append(f"- **Exit Code Unchanged:** {ec_diff['baseline']}")

            if var["stdout_diff"]:
                lines.append("\n**stdout Differences:**")
                lines.append("```diff")
                lines.append(var["stdout_diff"].strip())
                lines.append("```")
            else:
                lines.append("- **stdout:** Unchanged")

            if var["stderr_diff"]:
                lines.append("\n**stderr Differences:**")
                lines.append("```diff")
                lines.append(var["stderr_diff"].strip())
                lines.append("```")
            else:
                lines.append("- **stderr:** Unchanged")
            lines.append("")

    else:
        lines.append("=== CONFIGURATION EXPERIMENT REPORT ===")
        lines.append(f"Baseline Config: {comparison.get('baseline_config')}\n")
        lines.append("Summary:")
        for summary in comparison.get("runs_summary", []):
            status = "MATCH" if summary["matches_baseline"] else "DIFFERENT"
            c_name = summary["config_name"]
            c_code = summary["exit_code"]
            c_dur = summary["duration_sec"]
            s_str = f" - {c_name}: Exit {c_code}, Time {c_dur}s [{status}]"
            lines.append(s_str)

        lines.append("\nVariations:")
        for var in comparison.get("variations", []):
            lines.append(f"\n--- {var['config_name']} ---")
            ec_diff = var["exit_code_diff"]
            if ec_diff["changed"]:
                msg = (
                    f"Exit Code Changed: {ec_diff['baseline']} -> "
                    f"{ec_diff['current']}"
                )
                lines.append(msg)
            if var["stdout_diff"]:
                lines.append("stdout Diff:")
                lines.append(var["stdout_diff"].strip())
            if var["stderr_diff"]:
                lines.append("stderr Diff:")
                lines.append(var["stderr_diff"].strip())
            if (
                not ec_diff["changed"]
                and not var["stdout_diff"]
                and not var["stderr_diff"]
            ):
                lines.append("No behavioral differences detected.")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Run base command against config variations and report "
        "behavioral differences."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--command",
        required=True,
        help="Base command to execute. Use '{config}' as placeholder.",
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        required=True,
        help="Paths to configuration files to test against.",
    )
    parser.add_argument(
        "--env-var",
        default="CONFIG_FILE",
        help="Environment variable name for config file path.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Output report format (default: text).",
    )
    parser.add_argument(
        "--output",
        help="Output file path to write report to (default: stdout).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Execution timeout per run in seconds (default: 30.0).",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for config-experiment."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    results: List[RunResult] = []
    for cfg in parsed.configs:
        cfg_path = Path(cfg)
        result = run_single_config(
            command_template=parsed.command,
            config_path=cfg_path,
            env_var_name=parsed.env_var,
            timeout=parsed.timeout,
        )
        results.append(result)

    comparison = compare_results(results)
    report = generate_report(comparison, fmt=parsed.format)

    if parsed.output:
        Path(parsed.output).write_text(report, encoding="utf-8")
        print(f"Report written to {parsed.output}")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())

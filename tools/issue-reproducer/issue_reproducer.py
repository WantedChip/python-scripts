"""issue-reproducer: Unpacks bug bundles, creates venvs, and runs commands.

Re-runs failed commands under exact package snapshots to test reproducibility.
"""

import argparse
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import time
import zipfile
from typing import Any, Dict, Optional


def get_venv_paths(workspace: str) -> tuple[str, str]:
    """Get paths for python and pip executables in the virtual environment."""
    if sys.platform == "win32":
        venv_bin = os.path.join(workspace, ".venv", "Scripts")
        return (
            os.path.join(venv_bin, "python.exe"),
            os.path.join(venv_bin, "pip.exe"),
        )

    venv_bin = os.path.join(workspace, ".venv", "bin")
    return (os.path.join(venv_bin, "python"), os.path.join(venv_bin, "pip"))


def generate_reproduction_readme(
    original_cmd: str,
    orig_code: int,
    rep_code: int,
    reproduced: bool,
    stdout_differs: bool,
    stderr_differs: bool,
    duration: float,
) -> str:
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Generate a formatted markdown readme describing the reproduction details.

    Args:
        original_cmd: The command that was reproduced.
        orig_code: Original command exit code.
        rep_code: Reproduced command exit code.
        reproduced: Whether reproduction succeeded.
        stdout_differs: True if stdout differs between runs.
        stderr_differs: True if stderr differs between runs.
        duration: The reproduced run duration.

    Returns:
        Markdown string content for the README.
    """
    status = "REPRODUCED" if reproduced else "NOT REPRODUCED"
    return f"""# Issue Reproduction Workspace

This workspace was automatically generated.

## Diagnostics Summary

- **Reproduced Status**: `{status}`
- **Command Run**: `{original_cmd}`
- **Original Exit Code**: `{orig_code}`
- **Reproduction Exit Code**: `{rep_code}`
- **Reproduction Duration**: `{duration:.2f} seconds`
- **Output Validation**:
  - Stdout Differs: `{stdout_differs}`
  - Stderr Differs: `{stderr_differs}`

## Workspace Setup Details

This directory contains:
1. `.venv/` - Isolated Python venv matching original snapshot.
2. `stdout.log` & `stderr.log` - Original logs.
3. `reproduction_stdout.log` & `reproduction_stderr.log` - Logs.
4. `reproduction_report.json` - JSON report.

## Manual Instructions

To run manually:
1. Activate the virtual environment:
   - **Windows**: `.venv\\Scripts\\activate`
   - **Linux/macOS**: `source .venv/bin/activate`
2. Run the command:
   ```bash
   {original_cmd}
   ```
"""


class IssueReproducer:
    """Unpacks ZIP bundles, runs command, and evaluates reproducibility."""

    def __init__(self, bundle_path: str, workspace_path: Optional[str] = None) -> None:
        """Initialize the reproducer.

        Args:
            bundle_path: Path to the bug bundle ZIP.
            workspace_path: Target workspace path (temp dir if not supplied).
        """
        self.bundle_path = bundle_path
        self.workspace_path = workspace_path
        self.temp_dir_created = False

    def setup_workspace(self) -> str:
        """Create the workspace directory and unpack ZIP bundle.

        Returns:
            The workspace directory path.
        """
        if not self.workspace_path:
            self.workspace_path = tempfile.mkdtemp(prefix="repro_")
            self.temp_dir_created = True

        os.makedirs(self.workspace_path, exist_ok=True)

        with zipfile.ZipFile(self.bundle_path, "r") as zf:
            zf.extractall(self.workspace_path)

        return self.workspace_path

    def run_reproduction(self, workspace: str) -> Dict[str, Any]:
        # pylint: disable=too-many-locals
        """Create virtual environment, install package snapshot, and execute command.

        Args:
            workspace: The path to the unpacked workspace.

        Returns:
            A dictionary containing reproduction outputs, codes, and duration.
        """
        manifest_path = os.path.join(workspace, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest not found in bundle: {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        packages = manifest.get("packages", {})
        command = manifest.get("command", "")

        # Create virtualenv using standard sys.executable
        # pylint: disable=subprocess-run-check
        subprocess.run(
            [sys.executable, "-m", "venv", ".venv"],
            cwd=workspace,
            shell=False,
        )  # nosec B603

        python_path, pip_path = get_venv_paths(workspace)

        # 2. Write requirements.txt
        reqs_path = os.path.join(workspace, "requirements_snapshot.txt")
        with open(reqs_path, "w", encoding="utf-8") as f:
            for name, version in packages.items():
                f.write(f"{name}=={version}\n")

        # Restore dependency packages
        print("Restoring package dependencies snapshot...")
        if packages:
            subprocess.run(
                [pip_path, "install", "-r", "requirements_snapshot.txt"],
                cwd=workspace,
                shell=False,
            )  # nosec B603

        # Modify PATH to activate the virtual env for subprocess execution
        env = os.environ.copy()
        venv_bin = os.path.dirname(python_path)
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = os.path.join(workspace, ".venv")

        # Remove launcher env var to prevent macOS spawning global python
        env.pop("__PYVENV_LAUNCHER__", None)

        print(f"Executing target command: {command}")
        start_time = time.time()
        result = subprocess.run(
            command,
            shell=True,  # nosec B602 B603
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        duration = time.time() - start_time

        # Save reproduction outputs
        with open(
            os.path.join(workspace, "reproduction_stdout.log"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(result.stdout)
        with open(
            os.path.join(workspace, "reproduction_stderr.log"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(result.stderr)

        # Retrieve original output logs
        orig_stdout = ""
        orig_stderr = ""
        orig_stdout_path = os.path.join(workspace, "stdout.log")
        orig_stderr_path = os.path.join(workspace, "stderr.log")

        if os.path.exists(orig_stdout_path):
            with open(orig_stdout_path, "r", encoding="utf-8") as f:
                orig_stdout = f.read()
        if os.path.exists(orig_stderr_path):
            with open(orig_stderr_path, "r", encoding="utf-8") as f:
                orig_stderr = f.read()

        # Compare outputs
        orig_code = manifest.get("exit_code", 0)
        reproduced = result.returncode == orig_code and orig_code != 0
        stdout_differs = result.stdout != orig_stdout
        stderr_differs = result.stderr != orig_stderr

        # Generate README & JSON report
        readme_content = generate_reproduction_readme(
            command,
            orig_code,
            result.returncode,
            reproduced,
            stdout_differs,
            stderr_differs,
            duration,
        )
        with open(
            os.path.join(workspace, "reproduction_readme.md"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(readme_content)

        report = {
            "reproduced": reproduced,
            "original_exit_code": orig_code,
            "reproduction_exit_code": result.returncode,
            "original_command": command,
            "stdout_differs": stdout_differs,
            "stderr_differs": stderr_differs,
            "reproduction_duration_seconds": duration,
        }

        with open(
            os.path.join(workspace, "reproduction_report.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(report, f, indent=2)

        return report

    def cleanup(self) -> None:
        """Delete workspace directory if it was a temporary folder."""
        if self.temp_dir_created and self.workspace_path:
            shutil.rmtree(self.workspace_path, ignore_errors=True)


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Re-runs command from bug ZIP in venvs."
    )
    parser.add_argument("-b", "--bundle", required=True, help="Path to bug ZIP.")
    parser.add_argument(
        "-w",
        "--workspace",
        help="Workspace directory. Created as temp folder if omitted.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Retain workspace directory after completion.",
    )

    args = parser.parse_args()

    reproducer = IssueReproducer(args.bundle, args.workspace)
    workspace = ""
    try:
        workspace = reproducer.setup_workspace()
        print(f"Workspace initialized: {workspace}")
        report = reproducer.run_reproduction(workspace)

        print("\n--- Reproduction Results ---")
        print(f"Reproduced: {report['reproduced']}")
        print(f"Original Exit Code: {report['original_exit_code']}")
        print(f"Reproduction Exit Code: {report['reproduction_exit_code']}")
        print(f"Duration: {report['reproduction_duration_seconds']:.2f}s")
        print(f"Readme report written to: {workspace}/reproduction_readme.md")
    finally:
        if not args.keep and reproducer.temp_dir_created:
            print("Cleaning up temporary workspace...")
            reproducer.cleanup()
        elif reproducer.temp_dir_created:
            print(f"Temporary workspace kept at: {workspace}")


if __name__ == "__main__":
    main()

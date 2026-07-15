"""command-doctor: Analyzes failed commands and stderrs to diagnose and resolve errors.

Detects:
- Missing executables in PATH
- Wrong working directory (missing files)
- Permission failures
- Port conflicts and identifying the process holding the port via psutil
- Virtual environment mistakes (global vs venv)
- PATH anomalies (duplicates, invalid paths)
"""

import argparse
import os
import re
import shlex
import shutil
import subprocess  # nosec B404
import sys
from typing import Any, Dict, List, Optional

psutil: Any = None
try:
    import psutil as ps_lib

    psutil = ps_lib
except ImportError:
    pass


def check_executable(cmd: str) -> Optional[str]:
    """Check if the executable in the command is missing from PATH.

    Args:
        cmd: The full command string.

    Returns:
        Diagnosis message if missing, else None.
    """
    args = shlex.split(cmd)
    if not args:
        return None

    exe = args[0]
    # If it's a relative path, check if it exists
    if os.path.sep in exe or (sys.platform == "win32" and "/" in exe):
        if not os.path.exists(exe):
            return (
                f"Executable '{exe}' is referenced by relative path "
                "but does not exist in the current working directory."
            )
        return None

    if not shutil.which(exe):
        return (
            f"Executable '{exe}' was not found in the system PATH. "
            "Verify name spelling or check if it needs to be installed."
        )
    return None


def check_missing_files(cmd: str) -> List[str]:
    """Check if file paths passed as arguments do not exist in CWD.

    Args:
        cmd: The full command string.

    Returns:
        List of missing file diagnostic messages.
    """
    args = shlex.split(cmd)
    if len(args) <= 1:
        return []

    diagnose = []
    for arg in args[1:]:
        # Simple heuristic to identify possible file paths
        if any(c in arg for c in (".", "/", "\\", "-")) and not arg.startswith("-"):
            # If it looks like a path, verify existence
            if not os.path.exists(arg):
                # Check if it exists with another separator or case
                alt_path = arg.replace("\\", "/").replace("/", os.path.sep)
                if os.path.exists(alt_path):
                    diagnose.append(
                        f"File '{arg}' does not exist, but '{alt_path}' "
                        "does. Check path separators."
                    )
                else:
                    diagnose.append(
                        f"Argument file path '{arg}' does not exist in the CWD."
                    )
    return diagnose


def check_permissions(stderr: str) -> Optional[str]:
    """Audit for PermissionError signatures in stderr.

    Args:
        stderr: The captured stderr stream.

    Returns:
        Diagnosis message if permission issue found, else None.
    """
    patterns = [
        r"PermissionError",
        r"Access is denied",
        r"Permission denied",
        r"EACCES",
    ]
    if any(re.search(pat, stderr, re.IGNORECASE) for pat in patterns):
        msg = "Detected a file or directory permission failure. "
        if sys.platform == "win32":
            msg += (
                "Try running the terminal as Administrator or check "
                "folder Security permissions."
            )
        else:
            msg += (
                "Try prefixing with 'sudo' or auditing file permissions "
                "using 'ls -l' / 'chmod'."
            )
        return msg
    return None


def check_port_conflicts(stderr: str) -> Optional[str]:
    """Scan connections via psutil if port binding error is detected.

    Args:
        stderr: The captured stderr stream.

    Returns:
        Diagnosis message mapping port owner details, else None.
    """
    patterns = [
        r"Address already in use",
        r"OSError: \[Errno 98\]",
        r"OSError: \[Errno 10048\]",
        r"bind.*already in use",
    ]
    if not any(re.search(pat, stderr, re.IGNORECASE) for pat in patterns):
        return None

    # Find the port number in the stderr (heuristic search)
    port_match = re.search(r"port\s+(\d+)", stderr, re.IGNORECASE)
    if not port_match:
        # Search for address like 0.0.0.0:8000 or 127.0.0.1:8000
        port_match = re.search(r":(\d+)", stderr)
    if not port_match:
        # Search for Python socket error tuple format like ('0.0.0.0', 8080)
        port_match = re.search(r",\s*(\d{2,5})\)", stderr)

    port = int(port_match.group(1)) if port_match else None

    msg = "Detected a port conflict binding error."
    if port and psutil:
        msg += f" Port: {port}\n"
        owner_found = False
        try:
            # pylint: disable=no-member
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr and conn.laddr.port == port:
                    pid = conn.pid
                    if pid:
                        proc = psutil.Process(pid)
                        msg += (
                            f"  - Owner Process: '{proc.name()}' (PID: {pid})\n"
                            f"  - Command Line: {' '.join(proc.cmdline())}\n"
                            f"  - Executable: {proc.exe()}"
                        )
                        owner_found = True
                        break
        except Exception as e:  # pylint: disable=broad-except
            msg += f" (Could not audit active port owners: {str(e)})"
            return msg

        if not owner_found:
            msg += " (No active local process is currently binding this port.)"
    elif port:
        msg += f" Port: {port} (Install psutil to identify the process owner)."
    else:
        msg += " (Port number could not be parsed from stderr.)"

    return msg


def check_virtual_env(cmd: str, stderr: str) -> List[str]:
    """Verify venv execution paths and package imports.

    Args:
        cmd: The full command string.
        stderr: The captured stderr stream.

    Returns:
        List of virtual environment diagnostic warnings.
    """
    diagnose = []
    args = shlex.split(cmd)
    if not args:
        return []

    exe = args[0]

    # Rule 1: Using global python instead of venv python
    if exe in ("python", "python3", "pip", "pip3"):
        # Check if running in a venv
        is_in_venv = "VIRTUAL_ENV" in os.environ or sys.prefix != getattr(
            sys, "base_prefix", sys.prefix
        )
        if not is_in_venv:
            # Look if there is a local .venv folder in CWD
            if os.path.isdir(".venv") or os.path.isdir("venv"):
                diagnose.append(
                    f"Command runs '{exe}' using global interpreter, but "
                    "a local virtual environment is present. Activate it "
                    "or run via '.venv\\Scripts\\python' / '.venv/bin/python'."
                )

    # Rule 2: ModuleNotFound / ImportError
    match = re.search(
        r"(?:ModuleNotFoundError|ImportError):\s+No\s+module\s+named\s+'([^']+)'",
        stderr,
    )
    if match:
        missing_module = match.group(1)
        diagnose.append(
            f"Python failed to import module '{missing_module}'. "
            f"Install it via 'pip install {missing_module}'."
        )

    return diagnose


def check_path_anomalies() -> List[str]:
    """Diagnose environment PATH directory configurations.

    Returns:
        List of PATH configuration anomalies.
    """
    diagnose = []
    path_env = os.environ.get("PATH", "")
    if not path_env:
        return ["Environment PATH is empty or not defined."]

    dirs = path_env.split(os.pathsep)
    seen = set()

    for idx, d in enumerate(dirs):
        if not d:
            continue
        # Rule 1: Duplicate entries
        if d in seen:
            diagnose.append(f"Duplicate PATH entry detected: '{d}' (position {idx}).")
            continue
        seen.add(d)

        # Rule 2: Invalid directories
        if not os.path.isdir(d):
            diagnose.append(f"Invalid PATH entry (does not exist): '{d}'.")

    return diagnose


class CommandDoctor:
    # pylint: disable=too-few-public-methods
    """Rules engine runner analyzing failures and mapping remediation layouts."""

    def __init__(
        self, command: Optional[str] = None, stderr_input: Optional[str] = None
    ) -> None:
        """Initialize the doctor.

        Args:
            command: Command string to execute.
            stderr_input: Captured stderr string.
        """
        self.command = command
        self.stderr_input = stderr_input

    def diagnose(self) -> Dict[str, Any]:
        """Execute command and run diagnostics rules against status and outputs.

        Returns:
            Dictionary containing issues, recommendations, exit_code, and outputs.
        """
        stderr = self.stderr_input or ""
        exit_code = 0
        stdout = ""

        if self.command and not self.stderr_input:
            # Run command to capture stderr
            print(f"Executing target command: {self.command}")
            # pylint: disable=subprocess-run-check
            result = subprocess.run(
                self.command,
                shell=True,  # nosec B602 B603
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode

        issues = []
        recommendations = []

        # Rule 1: Executable checks
        if self.command:
            exe_err = check_executable(self.command)
            if exe_err:
                issues.append(exe_err)
                recommendations.append("Check executable name or install it.")

            # Rule 2: File existence
            file_errs = check_missing_files(self.command)
            for err in file_errs:
                issues.append(err)
                recommendations.append("Verify working directory or file paths.")

        # Rule 3: Permissions
        perm_err = check_permissions(stderr)
        if perm_err:
            issues.append(perm_err)
            recommendations.append("Change file ownership or run as administrator.")

        # Rule 4: Port conflicts
        port_err = check_port_conflicts(stderr)
        if port_err:
            issues.append(port_err)
            recommendations.append(
                "Terminate process holding the port or change target port."
            )

        # Rule 5: Virtual environment checks
        if self.command:
            venv_errs = check_virtual_env(self.command, stderr)
            for err in venv_errs:
                issues.append(err)
                recommendations.append(
                    "Activate virtual environment or install dependencies."
                )

        # Rule 6: PATH check
        path_errs = check_path_anomalies()
        # Only log first 3 PATH anomalies to prevent output spam
        for err in path_errs[:3]:
            issues.append(f"PATH warning: {err}")
            recommendations.append("Clean up environment PATH configuration.")

        return {
            "issues": issues,
            "recommendations": list(set(recommendations)),
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
        }


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Diagnose failed command executions and environment setups."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-c", "--command", help="Command to run and diagnose.")
    group.add_argument(
        "-s",
        "--stderr",
        help="Text block of stderr logs or file containing stderr logs.",
    )

    args = parser.parse_args()

    stderr_content = None
    if args.stderr:
        if os.path.isfile(args.stderr):
            with open(args.stderr, "r", encoding="utf-8", errors="ignore") as f:
                stderr_content = f.read()
        else:
            stderr_content = args.stderr

    doctor = CommandDoctor(command=args.command, stderr_input=stderr_content)
    result = doctor.diagnose()

    print("\n" + "=" * 50)
    print("         COMMAND DIAGNOSTIC REPORT")
    print("=" * 50)
    if args.command:
        print(f"Command: {args.command}")
        print(f"Exit Code: {result['exit_code']}")
    else:
        print("Input: Manual Stderr Log Analysis")

    print("\n--- Detected Issues ---")
    if not result["issues"]:
        print("No immediate issues detected. Command might have run successfully.")
    else:
        for idx, issue in enumerate(result["issues"], 1):
            print(f"{idx}. {issue}")

    print("\n--- Recommended Actions ---")
    if not result["recommendations"]:
        print("None. Verify stderr content or system dependencies.")
    else:
        for idx, rec in enumerate(result["recommendations"], 1):
            print(f"{idx}. {rec}")
    print("=" * 50)


if __name__ == "__main__":
    main()

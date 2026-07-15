"""error-bundler: Sanitizes and packages system diagnostics on command failure.

Saves:
- Traceback / stdout / stderr
- Environment variables (sanitized)
- Installed package versions
- OS and system diagnostics
- Local configurations and recent logs (sanitized)
"""

import argparse
import importlib.metadata
import json
import os
import platform
import re
import subprocess  # nosec B404
import time
import zipfile
from typing import Any, Dict, List, Optional, Set

# List of keywords that indicate a sensitive environment variable or config value
SENSITIVE_KEYWORDS = {
    "KEY",
    "PASS",
    "SECRET",
    "TOKEN",
    "AUTH",
    "PWD",
    "SIGNATURE",
    "CERT",
    "CREDENTIAL",
    "DATABASE_URL",
    "CONN_STR",
}


def sanitize_value(key: str, value: str) -> str:
    """Mask a value if the key is determined to be sensitive.

    Args:
        key: The configuration or environment key name.
        value: The raw string value.

    Returns:
        The sanitized string value.
    """
    key_upper = key.upper()
    if any(kw in key_upper for kw in SENSITIVE_KEYWORDS):
        return "[SANITIZED]"
    return value


def sanitize_text_content(content: str) -> str:
    """Sanitize secrets in configuration or log file lines.

    Args:
        content: The raw text content.

    Returns:
        The sanitized text content.
    """
    lines = []
    # Match standard assignment patterns: KEY = VALUE or KEY: VALUE
    pattern = re.compile(r"^(\s*[^#=\s:]*[a-zA-Z_0-9]+[^#=\s:]*)\s*([=:])\s*(.*)$")
    for line in content.splitlines():
        match = pattern.match(line)
        if match:
            key, sep, val = match.groups()
            sanitized = sanitize_value(key, val)
            lines.append(f"{key}{sep}{sanitized}")
        else:
            lines.append(line)
    return "\n".join(lines)


def get_system_diagnostics() -> Dict[str, str]:
    """Retrieve non-sensitive platform and OS metadata.

    Returns:
        A dictionary of system metadata.
    """
    return {
        "os_name": os.name,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
    }


def get_installed_packages() -> Dict[str, str]:
    """Retrieve names and versions of installed packages in active environment.

    Returns:
        A dictionary of package names mapped to versions.
    """
    packages = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            packages[name.lower()] = dist.version
    return packages


def collect_recent_files(
    cwd: str, file_patterns: List[str], max_files: int = 10
) -> List[str]:
    """Search CWD for log files and configs, returning paths to bundle.

    Args:
        cwd: Base directory to search.
        file_patterns: Glob patterns to search for.
        max_files: Max files to collect.

    Returns:
        List of matching file paths.
    """
    collected = []
    # Ignore common massive or binary folders
    exclude_dirs = {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
    }

    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            for pattern in file_patterns:
                # Compile glob pattern into simple regex
                regex_pat = re.escape(pattern).replace(r"\*", ".*")
                if re.match(f"^{regex_pat}$", file):
                    full_path = os.path.join(root, file)
                    collected.append(full_path)
                    if len(collected) >= max_files:
                        return collected
    return collected


class ErrorBundler:
    """Orchestrates execution, diagnostic parsing, and zip compilation."""

    def __init__(
        self,
        command: Optional[str] = None,
        stderr_input: Optional[str] = None,
        custom_sanitize_keys: Optional[Set[str]] = None,
    ) -> None:
        """Initialize the bundler configuration.

        Args:
            command: Command to execute.
            stderr_input: Pre-existing traceback/stderr dump.
            custom_sanitize_keys: Custom environment keys to sanitize.
        """
        self.command = command
        self.stderr_input = stderr_input
        self.sanitize_keys = custom_sanitize_keys or set()

    def run_and_diagnose(self) -> Dict[str, Any]:
        """Run the command, capture metrics, and check status.

        Returns:
            Dictionary containing stdout, stderr, exit_code, and duration.
        """
        if not self.command:
            return {
                "stdout": "",
                "stderr": self.stderr_input or "",
                "exit_code": 1,
                "duration": 0.0,
            }

        start_time = time.time()
        # Run command in sub-process
        # pylint: disable=subprocess-run-check
        result = subprocess.run(
            self.command,
            shell=True,  # nosec B602 B603
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        duration = time.time() - start_time

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "duration": duration,
        }

    def bundle(self, output_path: str, log_patterns: List[str]) -> str:
        # pylint: disable=too-many-locals
        """Assemble environment context, sanitize, and write zip archive.

        Args:
            output_path: Target zip file location.
            log_patterns: File search patterns.

        Returns:
            The absolute path of the generated bundle.
        """
        diag = self.run_and_diagnose()

        # Sanitize env vars
        env_vars = {}
        for k, v in os.environ.items():
            if k in self.sanitize_keys:
                env_vars[k] = "[SANITIZED]"
            else:
                env_vars[k] = sanitize_value(k, v)

        manifest = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "command": self.command or "Manual Traceback Import",
            "exit_code": diag["exit_code"],
            "duration_seconds": diag["duration"],
            "system": get_system_diagnostics(),
            "packages": get_installed_packages(),
            "environment_variables": env_vars,
        }

        # Create zip bundle
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Write manifest
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            # Write outputs
            zf.writestr("stdout.log", diag["stdout"])
            zf.writestr("stderr.log", diag["stderr"])

            # Search and bundle config / log files
            recent_files = collect_recent_files(
                os.getcwd(), log_patterns + ["*.env", "pyproject.toml"]
            )
            for file_path in recent_files:
                if not os.path.exists(file_path):
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    sanitized_content = sanitize_text_content(content)
                    # Use relative path in zip to avoid local path leaks
                    rel_zip_path = os.path.relpath(file_path, os.getcwd())
                    zf.writestr(rel_zip_path, sanitized_content)
                except Exception as e:  # pylint: disable=broad-except
                    # Silently skip file if unreadable/locked
                    zf.writestr(
                        f"errors/{os.path.basename(file_path)}.err",
                        f"Error reading file: {str(e)}",
                    )

        return os.path.abspath(output_path)


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Creates a sanitized debug bundle of command or crash details."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-c", "--command", help="Command to execute and profile.")
    group.add_argument(
        "-s", "--stderr", help="File path containing raw stderr / traceback dump."
    )

    parser.add_argument(
        "-o",
        "--output",
        help="Target ZIP archive path. Defaults to error_bundle_<timestamp>.zip",
    )
    parser.add_argument(
        "--log-patterns",
        nargs="+",
        default=["*.log"],
        help="Glob patterns of files to collect in CWD (e.g. *.log error.txt).",
    )
    parser.add_argument(
        "--sanitize-keys",
        nargs="+",
        default=[],
        help="Custom environment variable names to sanitize.",
    )

    args = parser.parse_args()

    # Determine traceback input if -s is provided
    stderr_content = None
    if args.stderr:
        if os.path.isfile(args.stderr):
            with open(args.stderr, "r", encoding="utf-8", errors="ignore") as f:
                stderr_content = f.read()
        else:
            stderr_content = args.stderr

    # Determine default output file
    output_zip = args.output
    if not output_zip:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_zip = f"error_bundle_{timestamp}.zip"

    bundler = ErrorBundler(
        command=args.command,
        stderr_input=stderr_content,
        custom_sanitize_keys=set(args.sanitize_keys),
    )

    print("Analyzing and building error bundle...")
    bundle_path = bundler.bundle(output_zip, args.log_patterns)
    print(f"Bundle successfully created: {bundle_path}")


if __name__ == "__main__":
    main()

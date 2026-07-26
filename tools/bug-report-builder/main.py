"""Bug Report Builder CLI Tool.

Captures output from failed commands or log files, sanitizes sensitive info,
gathers environment details, and compiles comprehensive issue reports.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import dataclasses
import json
import os
import platform
import re
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REDACTED = "[REDACTED]"

# Regex patterns for identifying sensitive credentials and tokens
SENSITIVE_PATTERNS: List[Tuple[str, str]] = [
    # AWS Access Key ID
    (r"\b(AKIA[0-9A-Z]{16})\b", REDACTED),
    # Bearer Tokens
    (r"(?i)\b(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", rf"\1{REDACTED}"),
    # Basic Auth / Generic API Tokens in URLs
    (r"(https?://)([^:\s]+):([^@\s]+)@", rf"\1\2:{REDACTED}@"),
    # RSA / PEM Private Keys
    (
        r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?"
        r"-----END [A-Z ]+PRIVATE KEY-----",
        REDACTED,
    ),
    # JSON Web Tokens (JWT)
    (r"\beyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\b", REDACTED),
    # Generic Key-Value secret assignments
    (
        r"(?i)\b(api_key|apikey|secret|password|passwd|token|access_token|"
        r"auth_token|private_key|client_secret)\b(\s*[:=]\s*)(['\"]?)"
        r"[^\s'\";]+(\3)",
        rf"\1\2\3{REDACTED}\3",
    ),
]

SENSITIVE_ENV_KEYWORDS = {
    "SECRET",
    "PASSWORD",
    "PASS",
    "TOKEN",
    "KEY",
    "AUTH",
    "CREDENTIAL",
    "DATABASE_URL",
    "CONN_STR",
    "PRIVATE",
}


@dataclasses.dataclass
class BugReport:
    """Structure representing a gathered bug report."""

    title: str
    timestamp: str
    environment: Dict[str, Any]
    sanitized_env_vars: Dict[str, str]
    command: Optional[str]
    return_code: Optional[int]
    duration_seconds: Optional[float]
    stdout: str
    stderr: str
    log_content: Optional[str]
    expected_behavior: str
    actual_behavior: str
    attachments: List[Dict[str, str]]


def sanitize_text(text: str, custom_mask_keys: Optional[List[str]] = None) -> str:
    """Sanitize text by redacting sensitive secrets, keys, and tokens.

    Args:
        text: Input string to sanitize.
        custom_mask_keys: Optional list of additional strings/keys to redact.

    Returns:
        Sanitized string with sensitive information redacted.
    """
    if not text:
        return text

    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized)

    if custom_mask_keys:
        for key in custom_mask_keys:
            if key and len(key) > 2:
                sanitized = sanitized.replace(key, REDACTED)

    return sanitized


def get_sanitized_env_vars(
    extra_mask_keys: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Retrieve environment variables with sensitive keys redacted.

    Args:
        extra_mask_keys: Extra environment variable names to redact.

    Returns:
        Dictionary of environment variable names to values or REDACTED notices.
    """
    extra_set = set(extra_mask_keys or [])
    result: Dict[str, str] = {}

    for key, value in os.environ.items():
        key_upper = key.upper()
        is_sensitive = any(kw in key_upper for kw in SENSITIVE_ENV_KEYWORDS)
        if is_sensitive or key in extra_set:
            result[key] = REDACTED
        else:
            result[key] = sanitize_text(value, extra_mask_keys)

    return result


def get_system_environment() -> Dict[str, Any]:
    """Collect platform, OS, Python runtime, and environment metadata."""
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
    }


def run_command(command: str, cwd: Optional[str] = None) -> Tuple[int, str, str, float]:
    """Execute a command in a subprocess and record performance and output.

    Args:
        command: Command line string to run.
        cwd: Optional working directory path.

    Returns:
        Tuple of (exit_code, stdout_str, stderr_str, duration_seconds).
    """
    start_time = time.time()
    try:
        with subprocess.Popen(  # nosec B602 B603
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        ) as process:
            stdout_raw, stderr_raw = process.communicate()
            duration = time.time() - start_time
            ret = process.returncode
            out = stdout_raw or ""
            err = stderr_raw or ""
            return ret, out, err, round(duration, 3)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        duration = time.time() - start_time
        err_msg = f"Failed to execute command: {exc}"
        return -1, "", err_msg, round(duration, 3)


def read_attachment(file_path: str) -> Dict[str, str]:
    """Read attachment file content and sanitize it.

    Args:
        file_path: Path to the target file.

    Returns:
        Dictionary with filename and sanitized file content.
    """
    path = Path(file_path)
    if not path.is_file():
        err = f"[Error: File not found: {file_path}]"
        return {"file_name": path.name, "content": err}

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        return {"file_name": path.name, "content": sanitize_text(content)}
    except (OSError, IOError, ValueError) as exc:
        err = f"[Error reading file: {exc}]"
        return {"file_name": path.name, "content": err}


def compile_markdown_report(report: BugReport) -> str:
    """Format a BugReport object into GitHub-flavored Markdown.

    Args:
        report: The BugReport dataclass object.

    Returns:
        Formatted markdown string.
    """
    lines = [
        f"# Bug Report: {report.title}",
        "",
        f"**Generated:** {report.timestamp}",
        "",
        "## Summary",
        "",
        "### Expected Behavior",
        report.expected_behavior or "*No expected behavior provided.*",
        "",
        "### Actual Behavior",
        report.actual_behavior or "*No actual behavior provided.*",
        "",
        "## System & Environment Details",
        "",
        "| Attribute | Value |",
        "| --- | --- |",
    ]

    for k, v in report.environment.items():
        lines.append(f"| **{k}** | `{v}` |")

    lines.extend(
        [
            "",
            "<details>",
            "<summary>Environment Variables (Sanitized)</summary>",
            "",
            "```ini",
        ]
    )
    for k in sorted(report.sanitized_env_vars.keys()):
        lines.append(f"{k}={report.sanitized_env_vars[k]}")
    lines.extend(
        [
            "```",
            "</details>",
            "",
        ]
    )

    if report.command is not None:
        lines.extend(
            [
                "## Command Execution",
                "",
                f"**Command:** `{report.command}`",
                f"**Exit Code:** `{report.return_code}`",
                f"**Duration:** `{report.duration_seconds} seconds`",
                "",
            ]
        )

        if report.stdout:
            lines.extend(
                [
                    "### Standard Output (stdout)",
                    "```text",
                    report.stdout.strip(),
                    "```",
                    "",
                ]
            )

        if report.stderr:
            lines.extend(
                [
                    "### Standard Error (stderr)",
                    "```text",
                    report.stderr.strip(),
                    "```",
                    "",
                ]
            )

    if report.log_content:
        lines.extend(
            [
                "## Log Output",
                "```text",
                report.log_content.strip(),
                "```",
                "",
            ]
        )

    if report.attachments:
        lines.extend(["## Attachments", ""])
        for att in report.attachments:
            lines.extend(
                [
                    f"### {att['file_name']}",
                    "```text",
                    att["content"].strip(),
                    "```",
                    "",
                ]
            )

    return "\n".join(lines)


def compile_json_report(report: BugReport) -> str:
    """Format a BugReport object into JSON string format.

    Args:
        report: The BugReport dataclass object.

    Returns:
        JSON string representation of the report.
    """
    data = dataclasses.asdict(report)
    return json.dumps(data, indent=2)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Build sanitized issue reports from failed commands or log files."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-c",
        "--command",
        help="Failing command line string to execute and capture.",
    )
    parser.add_argument(
        "-l", "--log-file", help="Path to log file to read and sanitize."
    )
    parser.add_argument(
        "--expected", default="", help="Description of expected behavior."
    )
    parser.add_argument("--actual", default="", help="Description of actual behavior.")
    parser.add_argument(
        "--title",
        default="Command Execution Failure",
        help="Title of the report.",
    )
    parser.add_argument(
        "--attachment",
        action="append",
        dest="attachments",
        help="Path to attachment file (can be used multiple times).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path (prints to stdout if omitted).",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--mask-env",
        action="append",
        help="Additional environment variable name to sanitize.",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main execution point for bug-report-builder CLI tool."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.command and not parsed.log_file:
        err_msg = "Error: Either --command or --log-file must be specified."
        print(err_msg, file=sys.stderr)
        return 1

    stdout_clean = ""
    stderr_clean = ""
    ret_code = None
    duration = None
    cmd_str = None

    if parsed.command:
        cmd_str = parsed.command
        ret_code, stdout_raw, stderr_raw, duration = run_command(parsed.command)
        stdout_clean = sanitize_text(stdout_raw, parsed.mask_env)
        stderr_clean = sanitize_text(stderr_raw, parsed.mask_env)

    log_clean = None
    if parsed.log_file:
        log_path = Path(parsed.log_file)
        if log_path.is_file():
            raw_log = log_path.read_text(encoding="utf-8", errors="replace")
            log_clean = sanitize_text(raw_log, parsed.mask_env)
        else:
            msg = f"Warning: Log file not found: {parsed.log_file}"
            print(msg, file=sys.stderr)

    attached_files = []
    if parsed.attachments:
        for att_path in parsed.attachments:
            attached_files.append(read_attachment(att_path))

    sys_info = get_system_environment()
    env_vars = get_sanitized_env_vars(parsed.mask_env)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    report = BugReport(
        title=parsed.title,
        timestamp=timestamp,
        environment=sys_info,
        sanitized_env_vars=env_vars,
        command=cmd_str,
        return_code=ret_code,
        duration_seconds=duration,
        stdout=stdout_clean,
        stderr=stderr_clean,
        log_content=log_clean,
        expected_behavior=sanitize_text(parsed.expected, parsed.mask_env),
        actual_behavior=sanitize_text(parsed.actual, parsed.mask_env),
        attachments=attached_files,
    )

    if parsed.format == "json":
        output_content = compile_json_report(report)
    else:
        output_content = compile_markdown_report(report)

    if parsed.output:
        out_path = Path(parsed.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_content, encoding="utf-8")
        print(f"Report successfully saved to: {parsed.output}")
    else:
        print(output_content)

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Output Drift Checker.

Validate documentation code block execution against actual outputs.
Extracts shell command executions ($ command -> output) from Markdown documentation,
reruns commands, normalizes volatile fields (timestamps, PIDs, paths, UUIDs, addresses),
and alerts when documentation outputs have drifted from actual execution results.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-few-public-methods,too-many-instance-attributes

import argparse
import difflib
import json
import re
import subprocess  # nosec B404
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class CommandSnippet:
    """Represents a command execution example extracted from Markdown."""

    file_path: str
    line_number: int
    command: str
    expected_output: str
    full_block: str


@dataclass
class DriftResult:
    """Result of running and comparing a documentation command snippet."""

    file_path: str
    line_number: int
    command: str
    expected_output: str
    actual_output: str
    normalized_expected: str
    normalized_actual: str
    has_drift: bool
    diff: str


def normalize_volatile_fields(text: str) -> str:
    """Normalize volatile elements (timestamps, paths, PIDs, UUIDs, addresses)."""
    # Normalize ISO Datestamps: 2026-07-24T19:36:48 or 2026-07-24 19:36:48
    norm = re.sub(
        r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
        "<TIMESTAMP>",
        text,
    )
    # Normalize simple dates: 2026-07-24 or 24/07/2026
    norm = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}/\d{2}/\d{4}\b", "<DATE>", norm)
    # Normalize simple times: 19:36:48
    norm = re.sub(r"\b\d{2}:\d{2}:\d{2}\b", "<TIME>", norm)

    # Normalize UUIDs: e.g. 550e8400-e29b-41d4-a716-446655440000
    uuid_pattern = (
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )
    norm = re.sub(uuid_pattern, "<UUID>", norm)

    # Normalize hex memory addresses: 0x7ffc82a10b
    norm = re.sub(r"\b0x[0-9a-fA-F]+\b", "<ADDR>", norm)

    # Normalize SHA256 hashes (64 hex chars)
    norm = re.sub(r"\b[0-9a-fA-F]{64}\b", "<HASH>", norm)

    # Normalize Process IDs: PID 12345 or [PID: 123]
    norm = re.sub(r"\bPID[:=\s]+\d+\b", "PID <PID>", norm, flags=re.IGNORECASE)

    # Normalize file paths (Unix / Windows absolute paths)
    norm = re.sub(r"(?:[a-zA-Z]:\\|/)[^\s:\"']+", "<PATH>", norm)

    # Normalize durations: e.g. 10.5ms, 2.3s
    norm = re.sub(r"\b\d+(?:\.\d+)?(?:ms|µs|ns|sec|s)\b", "<DURATION>", norm)

    return norm.strip()


def extract_snippets_from_markdown(file_path: Path) -> List[CommandSnippet]:
    """Extract '$ command' and expected output snippets from markdown files."""
    snippets: List[CommandSnippet] = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return snippets

    # Match code blocks labeled bash/sh/console/shell or unlabelled ```
    block_regex = re.compile(
        r"```(?:bash|sh|console|shell|cmd|powershell)?\s*\n(.*?)```", re.DOTALL
    )

    for match in block_regex.finditer(content):
        block_text = match.group(1)
        start_char = match.start()
        line_no = content[:start_char].count("\n") + 1

        lines = block_text.splitlines()
        cmd_idx = -1
        current_cmd = ""
        expected_lines: List[str] = []

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("$ ") or stripped.startswith("> "):
                if current_cmd:
                    snippets.append(
                        CommandSnippet(
                            file_path=str(file_path),
                            line_number=line_no + cmd_idx,
                            command=current_cmd,
                            expected_output="\n".join(expected_lines).strip(),
                            full_block=block_text,
                        )
                    )
                    expected_lines = []
                cmd_idx = idx
                current_cmd = stripped[2:].strip()
            elif current_cmd:
                expected_lines.append(line)

        if current_cmd:
            snippets.append(
                CommandSnippet(
                    file_path=str(file_path),
                    line_number=line_no + cmd_idx,
                    command=current_cmd,
                    expected_output="\n".join(expected_lines).strip(),
                    full_block=block_text,
                )
            )

    return snippets


def run_command_snippet(
    snippet: CommandSnippet, timeout: int = 10, cwd: Optional[Path] = None
) -> DriftResult:
    """Execute command snippet and check for drift against expected output."""
    work_dir = str(cwd or Path(snippet.file_path).parent)
    actual_output = ""

    try:
        proc = subprocess.run(  # nosec B602
            snippet.command,
            shell=True,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        actual_output = proc.stdout.strip()
    except subprocess.TimeoutExpired:
        actual_output = "[ERROR] Command execution timed out"
    except Exception as e:  # pylint: disable=broad-exception-caught
        actual_output = f"[ERROR] Command failed: {e}"

    norm_expected = normalize_volatile_fields(snippet.expected_output)
    norm_actual = normalize_volatile_fields(actual_output)

    has_drift = norm_expected != norm_actual

    diff_str = ""
    if has_drift:
        diff_lines = difflib.unified_diff(
            norm_expected.splitlines(),
            norm_actual.splitlines(),
            fromfile="expected (normalized)",
            tofile="actual (normalized)",
            lineterm="",
        )
        diff_str = "\n".join(diff_lines)

    return DriftResult(
        file_path=snippet.file_path,
        line_number=snippet.line_number,
        command=snippet.command,
        expected_output=snippet.expected_output,
        actual_output=actual_output,
        normalized_expected=norm_expected,
        normalized_actual=norm_actual,
        has_drift=has_drift,
        diff=diff_str,
    )


def update_markdown_file(file_path: Path, results: List[DriftResult]) -> None:
    """Update markdown documentation with actual command outputs."""
    content = file_path.read_text(encoding="utf-8")

    for res in results:
        if res.has_drift and not res.actual_output.startswith("[ERROR]"):
            pat_str = (
                re.escape(f"$ {res.command}")
                + r"\s*\n"
                + re.escape(res.expected_output)
            )
            replacement = f"$ {res.command}\n{res.actual_output}"
            content = re.sub(pat_str, replacement, content)

    file_path.write_text(content, encoding="utf-8")


def format_text_report(results: List[DriftResult]) -> str:
    """Format drift results into readable terminal text."""
    drift_count = sum(1 for r in results if r.has_drift)
    if drift_count == 0:
        return (
            f"All {len(results)} documentation command outputs match "
            "actual execution results!"
        )

    hdr = (
        f"=== Output Drift Report ({drift_count}/{len(results)} "
        "snippets drifted) ==="
    )
    lines = [hdr, ""]
    for r in results:
        if r.has_drift:
            lines.append(f"[DRIFT DETECTED] {r.file_path}:{r.line_number}")
            lines.append(f"  Command: $ {r.command}")
            lines.append("  Diff:")
            for d in r.diff.splitlines():
                lines.append(f"    {d}")
            lines.append("-" * 60)
    return "\n".join(lines)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = "Verify Markdown documentation command outputs against actual execution."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Markdown file or directory to audit",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Auto-update outdated markdown code block outputs",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Command execution timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint for output-drift."""
    parsed = parse_args(args)
    target_path = Path(parsed.path).resolve()

    if not target_path.exists():
        print(f"Error: Target path '{target_path}' does not exist.", file=sys.stderr)
        return 1

    if target_path.is_file():
        files = [target_path]
    else:
        files = list(target_path.rglob("*.md"))

    all_snippets: List[CommandSnippet] = []
    for f in files:
        all_snippets.extend(extract_snippets_from_markdown(f))

    if not all_snippets:
        print("No command snippets ($ command) found in target Markdown file(s).")
        return 0

    results: List[DriftResult] = []
    for snippet in all_snippets:
        res = run_command_snippet(snippet, timeout=parsed.timeout)
        results.append(res)

    if parsed.update:
        file_results: Dict[str, List[DriftResult]] = {}
        for r in results:
            file_results.setdefault(r.file_path, []).append(r)
        for f_path, res_list in file_results.items():
            update_markdown_file(Path(f_path), res_list)
        print("Updated Markdown documentation files with actual command outputs.")

    if parsed.format == "json":
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        print(format_text_report(results))

    drift_count = sum(1 for r in results if r.has_drift)
    return 0 if drift_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

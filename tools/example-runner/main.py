"""Example Runner Tool.

Extracts code snippets (Python, Bash) from Markdown documentation,
executes them safely in isolated temporary environments, and flags broken
examples.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import re
import subprocess  # nosec B404
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union


@dataclass
class CodeSnippet:
    """Class representing an extracted Markdown code snippet."""

    file_path: Path
    line_number: int
    language: str
    code: str
    expected_output: Optional[str] = None


@dataclass
class ExecutionResult:
    """Result of running a code snippet."""

    snippet: CodeSnippet
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    message: str


CODE_BLOCK_PATTERN = re.compile(
    r"```(python|py|bash|sh)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE
)

EXPECTED_OUTPUT_PATTERN = re.compile(
    r"(?:#|//)\s*(?:Output|Expected):\s*(.*)", re.IGNORECASE
)


def extract_snippets_from_markdown(file_path: Path) -> List[CodeSnippet]:
    """Extract Python and Bash code blocks from Markdown files."""
    if not file_path.exists():
        return []

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    snippets: List[CodeSnippet] = []

    for match in CODE_BLOCK_PATTERN.finditer(content):
        lang = match.group(1).lower()
        code = match.group(2)
        start_pos = match.start()
        line_num = content[:start_pos].count("\n") + 1

        expected: Optional[str] = None
        output_match = EXPECTED_OUTPUT_PATTERN.search(code)
        if output_match:
            expected = output_match.group(1).strip()

        snippets.append(
            CodeSnippet(
                file_path=file_path,
                line_number=line_num,
                language=lang,
                code=code,
                expected_output=expected,
            )
        )

    return snippets


def execute_snippet(snippet: CodeSnippet, timeout: float = 15.0) -> ExecutionResult:
    """Execute a single snippet in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        cmd: Union[List[str], str]
        if snippet.language in ("python", "py"):
            script_file = tmp_path / "example.py"
            script_file.write_text(snippet.code, encoding="utf-8")
            cmd = [sys.executable, str(script_file)]
        else:
            script_file = tmp_path / "example.sh"
            script_file.write_text(snippet.code, encoding="utf-8")
            if sys.platform == "win32":
                cmd = f"powershell -Command {script_file}"
            else:
                cmd = f"bash {script_file}"

        try:
            proc = subprocess.run(  # nosec B602, B603
                cmd,
                shell=isinstance(cmd, str),
                capture_output=True,
                text=True,
                cwd=tmp_path,
                timeout=timeout,
                check=False,
            )

            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            passed = proc.returncode == 0

            msg = f"Exit code {proc.returncode}"
            if snippet.expected_output:
                if (
                    snippet.expected_output in stdout
                    or snippet.expected_output in stderr
                ):
                    msg += " (Expected output matched)"
                else:
                    passed = False
                    exp = snippet.expected_output
                    msg += f" (Expected '{exp}', got '{stdout}')"

            return ExecutionResult(
                snippet=snippet,
                passed=passed,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                message=msg,
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                snippet=snippet,
                passed=False,
                exit_code=-1,
                stdout="",
                stderr="",
                message=f"Execution timed out after {timeout} seconds",
            )
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            return ExecutionResult(
                snippet=snippet,
                passed=False,
                exit_code=-1,
                stdout="",
                stderr="",
                message=f"Execution error: {str(e)}",
            )


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Find and execute code snippets in Markdown documentation."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "paths",
        nargs="+",
        help="Markdown file paths or directories to scan.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Maximum snippet execution timeout in seconds (default: 15.0).",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for example-runner."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    files: List[Path] = []
    for p in parsed.paths:
        path = Path(p)
        if path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.md"))

    if not files:
        print("No Markdown files found.")
        return 0

    total_snippets = 0
    failed_snippets = 0

    print(f"Scanning {len(files)} Markdown file(s)...\n")

    for doc in files:
        snippets = extract_snippets_from_markdown(doc)
        if not snippets:
            continue

        print(f"--- Document: {doc} ({len(snippets)} snippet(s)) ---")
        for idx, snip in enumerate(snippets, start=1):
            total_snippets += 1
            res = execute_snippet(snip, timeout=parsed.timeout)

            status = "PASS" if res.passed else "FAIL"
            msg = (
                f"  [{status}] Snippet #{idx} (Line {snip.line_number}, "
                f"{snip.language}): {res.message}"
            )
            print(msg)

            if not res.passed:
                failed_snippets += 1
                if res.stderr:
                    print(f"    stderr: {res.stderr}")

        print()

    print("=== EXAMPLE RUNNER SUMMARY ===")
    print(f"Total Snippets Executed: {total_snippets}")
    print(f"Passed: {total_snippets - failed_snippets}")
    print(f"Failed: {failed_snippets}")

    if failed_snippets > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

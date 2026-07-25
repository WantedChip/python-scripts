"""Assumption Hunter: Scan source code for hidden environmental assumptions.

Identifies potential hardcoded environment assumptions (CWD, temp dirs,
encodings, timezones, shell binaries, path separators, env vars, etc.)
using AST and regex analysis.
"""

# pylint: disable=too-many-instance-attributes,too-many-arguments
# pylint: disable=too-many-positional-arguments,invalid-name,too-many-locals
# pylint: disable=too-many-branches

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Finding:
    """Represents a detected environmental assumption in source code."""

    file_path: str
    line: int
    column: int
    rule_id: str
    assumption_type: str
    severity: str
    snippet: str
    risk_explanation: str
    remediation_advice: str


class ASTAssumptionVisitor(ast.NodeVisitor):
    """AST visitor that checks for code-level environmental assumptions."""

    def __init__(self, filename: str, lines: List[str]) -> None:
        self.filename = filename
        self.lines = lines
        self.findings: List[Finding] = []

    def _get_snippet(self, line_no: int) -> str:
        if 1 <= line_no <= len(self.lines):
            return self.lines[line_no - 1].strip()
        return ""

    def _add_finding(
        self,
        node: ast.AST,
        rule_id: str,
        assumption_type: str,
        severity: str,
        risk: str,
        remediation: str,
    ) -> None:
        line = getattr(node, "lineno", 1)
        col = getattr(node, "col_offset", 0)
        snippet = self._get_snippet(line)
        self.findings.append(
            Finding(
                file_path=self.filename,
                line=line,
                column=col,
                rule_id=rule_id,
                assumption_type=assumption_type,
                severity=severity,
                snippet=snippet,
                risk_explanation=risk,
                remediation_advice=remediation,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        """Visit Call nodes to check for environmental assumptions."""
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        # Rule: MISSING_ENCODING for open / read_text / write_text
        file_funcs = ("open", "read_text", "write_text", "read_bytes", "write_bytes")
        if func_name in file_funcs:
            if func_name in ("open", "read_text", "write_text"):
                has_encoding = any(kw.arg == "encoding" for kw in node.keywords)
                # If mode is binary 'rb'/'wb', encoding is not required
                is_binary = False
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    arg_val = node.args[1].value
                    if isinstance(arg_val, str) and "b" in arg_val:
                        is_binary = True
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        if isinstance(kw.value.value, str) and "b" in kw.value.value:
                            is_binary = True

                if not has_encoding and not is_binary:
                    self._add_finding(
                        node,
                        "MISSING_ENCODING",
                        "Default System Encoding Assumption",
                        "MEDIUM",
                        (
                            "Opening file without explicit encoding defaults to "
                            "platform locale encoding (e.g. CP1252 on Windows), "
                            "breaking on UTF-8 files."
                        ),
                        "Specify explicit encoding parameter, e.g. open(..., "
                        "encoding='utf-8').",
                    )

        # Rule: LOCAL_TIMEZONE for datetime.now() / datetime.fromtimestamp()
        if func_name in ("now", "fromtimestamp"):
            if isinstance(node.func, ast.Attribute):
                val = node.func.value
                is_dt_name = isinstance(val, ast.Name) and val.id == "datetime"
                is_dt_attr = isinstance(val, ast.Attribute) and val.attr == "datetime"
                if is_dt_name or is_dt_attr:
                    min_args = 2 if func_name == "fromtimestamp" else 1
                    has_tz = (
                        any(kw.arg == "tz" for kw in node.keywords)
                        or len(node.args) >= min_args
                    )
                    if not has_tz:
                        self._add_finding(
                            node,
                            "LOCAL_TIMEZONE",
                            "Local Timezone Assumption",
                            "MEDIUM",
                            (
                                "Retrieving current time without explicit timezone "
                                "assumes local host timezone setting, causing "
                                "inconsistent behavior across servers."
                            ),
                            (
                                "Pass explicit timezone info, e.g. "
                                "datetime.now(timezone.utc)."
                            ),
                        )

        # Rule: CWD_DEPENDENCY for os.getcwd() or Path.cwd()
        if func_name in ("getcwd", "cwd"):
            self._add_finding(
                node,
                "CWD_DEPENDENCY",
                "Current Working Directory Assumption",
                "LOW",
                (
                    "Relying on CWD assumes script execution location and "
                    "breaks when called from arbitrary directories."
                ),
                (
                    "Use absolute paths derived relative to "
                    "Path(__file__).resolve().parent."
                ),
            )

        # Rule: UNSORTED_FILENAMES for os.listdir() or Path.iterdir() / glob.glob()
        if func_name in ("listdir", "iterdir", "glob", "rglob"):
            self._add_finding(
                node,
                "UNSORTED_FILENAMES",
                "Nondeterministic File Iteration Order Assumption",
                "LOW",
                (
                    "Directory listings and glob operations return "
                    "non-deterministic filesystem order across OS platforms."
                ),
                (
                    "Wrap file listings in sorted(), e.g. sorted(os.listdir(...)) "
                    "or sorted(Path.glob(...))."
                ),
            )

        # Rule: SPECIFIC_SHELL / shell=True in subprocess
        if func_name in ("run", "Popen", "call", "check_output", "check_call"):
            for kw in node.keywords:
                is_shell_true = (
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                )
                if is_shell_true:
                    self._add_finding(
                        node,
                        "SPECIFIC_SHELL",
                        "Subprocess Shell Execution Assumption",
                        "HIGH",
                        (
                            "Executing shell=True assumes availability of system "
                            "shell environment and introduces shell injection / "
                            "portability risks."
                        ),
                        "Pass command as arguments list with shell=False.",
                    )

        # Rule: GLOBAL_CLI_DEPENDENCY for subprocess calls
        if func_name in ("run", "Popen", "call", "check_output", "check_call"):
            if node.args and isinstance(node.args[0], ast.List) and node.args[0].elts:
                first_elt = node.args[0].elts[0]
                if isinstance(first_elt, ast.Constant) and isinstance(
                    first_elt.value, str
                ):
                    cmd_name = first_elt.value
                    if cmd_name not in ("python", "python3", sys.executable):
                        self._add_finding(
                            node,
                            "GLOBAL_CLI_DEPENDENCY",
                            "External CLI Dependency Assumption",
                            "MEDIUM",
                            (
                                f"Assumes external CLI tool '{cmd_name}' is "
                                "installed and present in system PATH."
                            ),
                            (
                                f"Verify executable presence using "
                                f"shutil.which('{cmd_name}') before executing."
                            ),
                        )

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Check for direct os.environ['VAR'] indexing assumptions."""
        val = node.value
        if isinstance(val, ast.Attribute):
            inner_val = getattr(val, "value", None)
            if (
                isinstance(inner_val, ast.Name)
                and inner_val.id == "os"
                and val.attr == "environ"
            ):
                self._add_finding(
                    node,
                    "ENV_VAR_EXISTENCE",
                    "Environment Variable Existence Assumption",
                    "MEDIUM",
                    (
                        "Direct dictionary indexing of os.environ raises KeyError "
                        "if environment variable is not defined on target system."
                    ),
                    "Use os.getenv('VAR', default) or os.environ.get('VAR').",
                )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            val = node.value

            # Rule: TMP_HARDCODED
            tmp_pat = r"^(?:/tmp|/var/tmp|c:\\temp|c:\\tmp)(?:/|\\|$)"
            if re.search(tmp_pat, val, re.IGNORECASE):
                self._add_finding(
                    node,
                    "TMP_HARDCODED",
                    "Hardcoded Temporary Directory Assumption",
                    "HIGH",
                    (
                        f"Hardcoded temp path '{val}' may not exist or be "
                        "writable across different platforms."
                    ),
                    "Use tempfile.gettempdir() or tempfile.TemporaryDirectory().",
                )

            # Rule: WRITABLE_HOME
            if re.search(r"^~[/\\]|/(?:home|Users)/[^/]+/\.config", val):
                self._add_finding(
                    node,
                    "WRITABLE_HOME",
                    "Writable User Home Directory Assumption",
                    "LOW",
                    (
                        "Assumes user home directory is writable, which fails "
                        "in read-only container environments."
                    ),
                    (
                        "Provide fallback storage in temp directory if home dir "
                        "is not writable."
                    ),
                )

        self.generic_visit(node)


def scan_file(file_path: Path) -> List[Finding]:
    """Scan a single Python file for environmental assumptions."""
    findings: List[Finding] = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:  # pylint: disable=broad-exception-caught
        return findings

    lines = content.splitlines()

    # AST scanning
    try:
        tree = ast.parse(content, filename=str(file_path))
        visitor = ASTAssumptionVisitor(str(file_path), lines)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    except SyntaxError:
        pass

    # Regex line scanning for non-AST checks or raw string patterns
    regex_checks = [
        (
            r"locale\.setlocale\(",
            "LOCALE_DEPENDENCY",
            "Global Locale Assumption",
            "HIGH",
            (
                "Modifying global locale affects thread-safety and "
                "string/number formatting across the process."
            ),
            "Avoid process-wide locale mutations; use explicit formatting.",
        ),
        (
            r"(?:urllib\.request|requests\.(?:get|post|put|delete)|"
            r"http\.client|socket\.connect)\(",
            "INTERNET_ACCESS",
            "Unbounded Network Access Assumption",
            "MEDIUM",
            "Assumes active external network connection and unblocked traffic.",
            "Add explicit socket timeouts and handle exceptions gracefully.",
        ),
        (
            r"['\"](?:bash|cmd\.exe|powershell\.exe|/bin/sh)['\"]",
            "SPECIFIC_SHELL",
            "Specific Shell Binary Assumption",
            "MEDIUM",
            (
                "Hardcoded shell executable path fails on systems with "
                "non-standard shell locations."
            ),
            "Use sys.executable or stdlib wrappers instead.",
        ),
        (
            r"split\(['\"]/['\"]\)",
            "UNIX_PATH_SEPARATORS",
            "Unix Path Separator Assumption",
            "LOW",
            "Splitting path strings on Unix slash '/' breaks on Windows paths.",
            "Use pathlib.Path parts or os.path.split() / os.path.normpath().",
        ),
    ]

    for idx, line in enumerate(lines, 1):
        for pattern, rule_id, name, severity, risk, remediation in regex_checks:
            if re.search(pattern, line):
                # Avoid duplicate findings on same line/rule
                if not any(f.line == idx and f.rule_id == rule_id for f in findings):
                    findings.append(
                        Finding(
                            file_path=str(file_path),
                            line=idx,
                            column=0,
                            rule_id=rule_id,
                            assumption_type=name,
                            severity=severity,
                            snippet=line.strip(),
                            risk_explanation=risk,
                            remediation_advice=remediation,
                        )
                    )

    return findings


def scan_directory(
    root_path: Path,
    exclude_patterns: Optional[List[str]] = None,
    ignore_rules: Optional[List[str]] = None,
    min_severity: str = "LOW",
) -> List[Finding]:
    """Recursively scan directory for assumption findings."""
    all_findings: List[Finding] = []
    default_ex = [
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
    ]
    excludes = set(exclude_patterns or default_ex)
    ignores = set(ignore_rules or [])

    severity_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    min_sev_val = severity_order.get(min_severity.upper(), 1)

    if root_path.is_file():
        files = [root_path]
    else:
        files = [
            p
            for p in root_path.rglob("*.py")
            if not any(ex in p.parts for ex in excludes)
        ]

    for file_path in files:
        file_findings = scan_file(file_path)
        for finding in file_findings:
            if finding.rule_id in ignores:
                continue
            sev_val = severity_order.get(finding.severity.upper(), 1)
            if sev_val >= min_sev_val:
                all_findings.append(finding)

    return all_findings


def format_text_report(findings: List[Finding]) -> str:
    """Format findings into text report."""
    if not findings:
        return "No environmental assumption risks detected."

    lines = [
        f"=== Assumption Hunter Audit Report ({len(findings)} issues found) ===",
        "",
    ]
    for f in findings:
        lines.append(f"[{f.severity}] {f.rule_id}: {f.assumption_type}")
        lines.append(f"  Location: {f.file_path}:{f.line}:{f.column}")
        lines.append(f"  Snippet:  {f.snippet}")
        lines.append(f"  Risk:     {f.risk_explanation}")
        lines.append(f"  Fix:      {f.remediation_advice}")
        lines.append("-" * 60)
    return "\n".join(lines)


def main() -> None:
    """Main CLI entrypoint for assumption-hunter."""
    parser = argparse.ArgumentParser(
        description=(
            "Scan Python project source code for hidden environmental " "assumptions."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Directory or file path to scan (default: current dir)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--ignore-rule",
        action="append",
        help="Rule ID to ignore (can be specified multiple times)",
    )
    parser.add_argument(
        "--exclude", action="append", help="Directory pattern to exclude"
    )
    parser.add_argument(
        "--min-severity",
        choices=["LOW", "MEDIUM", "HIGH"],
        default="LOW",
        help="Minimum severity level",
    )

    args = parser.parse_args()
    target_path = Path(args.path).resolve()

    if not target_path.exists():
        print(f"Error: Target path '{target_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    findings = scan_directory(
        target_path,
        exclude_patterns=args.exclude,
        ignore_rules=args.ignore_rule,
        min_severity=args.min_severity,
    )

    if args.format == "json":
        output = json.dumps([asdict(f) for f in findings], indent=2)
        print(output)
    else:
        print(format_text_report(findings))

    sys.exit(0 if not findings else 1)


if __name__ == "__main__":
    main()

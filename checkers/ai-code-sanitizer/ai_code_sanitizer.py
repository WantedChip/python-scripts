#!/usr/bin/env python3
"""AI Code Sanitizer.

Parses source code files to detect AI code generation anti-patterns such as
fake imports, duplicate helpers, placeholder comments, swallowed exceptions,
unnecessary abstractions, and non-functional tests.
"""

import argparse
import ast
import difflib
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any


def check_fake_imports(tree: ast.AST, file_path: Path) -> list[tuple[int, str]]:
    """Scan code for imports that do not exist locally or in system path.

    Args:
        tree: The AST of the code.
        file_path: The path of the scanned file (for local module resolving).

    Returns:
        List of findings as (line_no, message).
    """
    findings: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                module_name = name.name
                if not is_module_resolvable(module_name, file_path):
                    findings.append(
                        (
                            node.lineno,
                            f"Potentially fake or unresolvable import: '{module_name}'",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            # Handle relative imports (level > 0)
            if node.level > 0:
                continue
            if not is_module_resolvable(module_name, file_path):
                findings.append(
                    (
                        node.lineno,
                        f"Potentially fake or unresolvable import base: "
                        f"'{module_name}'",
                    )
                )
            else:
                # Check imported names if module can be safely loaded/inspected
                check_imported_members(node, module_name, findings)

    return findings


def is_module_resolvable(module_name: str, file_path: Path) -> bool:
    """Verify if a module name exists in python path or locally.

    Args:
        module_name: Name of module (e.g. 'math' or 'my_local_pkg').
        file_path: Current file path.

    Returns:
        True if resolvable, False otherwise.
    """
    # Check standard path / installed specs
    try:
        spec = importlib.util.find_spec(module_name.split(".")[0])
        if spec is not None:
            return True
    except Exception:  # pylint: disable=broad-exception-caught  # nosec B110
        pass

    # Check local relative files
    base_dir = file_path.parent
    parts = module_name.split(".")
    # Try directory path
    dir_path = base_dir.joinpath(*parts)
    if dir_path.is_dir() and dir_path.joinpath("__init__.py").exists():
        return True
    # Try file path
    py_file = base_dir.joinpath(*parts[:-1]) / f"{parts[-1]}.py"
    if py_file.exists():
        return True

    return False


def check_imported_members(
    node: ast.ImportFrom, module_name: str, findings: list[tuple[int, str]]
) -> None:
    """Verify if names imported from a module exist in the resolved spec.

    Args:
        node: The ImportFrom node.
        module_name: The base module name.
        findings: The findings list to mutate.
    """
    # Safe list of built-in modules we can import and inspect without side-effects
    inspectable_stdlib = {
        "math",
        "json",
        "os",
        "sys",
        "re",
        "datetime",
        "hashlib",
        "collections",
        "itertools",
        "pathlib",
        "shutil",
        "ast",
        "logging",
    }

    base_pkg = module_name.split(".")[0]
    if base_pkg in inspectable_stdlib:
        try:
            mod = importlib.import_module(module_name)
            for name in node.names:
                member = name.name
                if member != "*" and not hasattr(mod, member):
                    findings.append(
                        (
                            node.lineno,
                            f"Imported name '{member}' not found "
                            f"in module '{module_name}'",
                        )
                    )
        except Exception:  # pylint: disable=broad-exception-caught  # nosec B110
            pass


def get_normalized_function_body(node: ast.FunctionDef) -> str:
    """Serialize and normalize the function body string, removing docstrings.

    Args:
        node: The FunctionDef node.

    Returns:
        The normalized code string of the function body.
    """
    body_nodes = node.body
    # If the first statement is a docstring, skip it
    if (
        body_nodes
        and isinstance(body_nodes[0], ast.Expr)
        and isinstance(body_nodes[0].value, ast.Constant)
        and isinstance(body_nodes[0].value.value, str)
    ):
        body_nodes = body_nodes[1:]

    # Parse and unparse AST back to clean string formatting
    try:
        return "\n".join(ast.unparse(n) for n in body_nodes).strip()
    except Exception:  # pylint: disable=broad-exception-caught
        return ""


def check_duplicate_helpers(tree: ast.AST) -> list[tuple[int, str]]:
    """Compare function definitions to identify duplicated helper implementations.

    Args:
        tree: The AST of the code.

    Returns:
        List of findings.
    """
    findings: list[tuple[int, str]] = []
    functions: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "body": get_normalized_function_body(node),
                }
            )

    # Pairwise comparison
    for i, f1 in enumerate(functions):
        for j in range(i + 1, len(functions)):
            f2 = functions[j]

            # 1. Body similarity check
            body1, body2 = f1["body"], f2["body"]
            if body1 and body2:
                ratio = difflib.SequenceMatcher(None, body1, body2).ratio()
                if ratio > 0.85:
                    findings.append(
                        (
                            f2["lineno"],
                            f"Function '{f2['name']}' is functionally identical "
                            f"to '{f1['name']}' (body similarity: {ratio:.2f})",
                        )
                    )
                    continue

            # 2. Name similarity check
            name1, name2 = f1["name"], f2["name"]
            n_ratio = difflib.SequenceMatcher(None, name1, name2).ratio()
            if n_ratio > 0.8:
                findings.append(
                    (
                        f2["lineno"],
                        f"Function '{f2['name']}' has highly similar name "
                        f"to '{f1['name']}' (name similarity: {n_ratio:.2f})",
                    )
                )

    return findings


def check_placeholder_comments(
    lines: list[str],
) -> list[tuple[int, str]]:
    """Scan raw code lines for common AI placeholder or TODO comments.

    Args:
        lines: Raw content lines.

    Returns:
        List of findings.
    """
    findings: list[tuple[int, str]] = []
    # Match strings like placeholder, your code here
    placeholder_regex = re.compile(
        r"#\s*(todo:\s*(implement|add\s+logic|write\s+code)|placeholder|"
        r"logic\s+goes\s+here|your\s+code\s+here)",
        re.I,
    )

    for idx, line in enumerate(lines, start=1):
        match = placeholder_regex.search(line)
        if match:
            findings.append(
                (
                    idx,
                    f"AI placeholder comment detected: '{line.strip()}'",
                )
            )

    return findings


def is_handler_swallowed(handler: ast.ExceptHandler) -> bool:
    """Check if exception handler body contains no raise and no substance.

    Args:
        handler: The ExceptHandler AST node.

    Returns:
        True if the handler swallowed the exception, False otherwise.
    """
    has_raise = False
    has_substance = False

    for stmt in ast.walk(handler):
        if isinstance(stmt, ast.Raise):
            has_raise = True
        elif isinstance(stmt, (ast.Assign, ast.Call, ast.Assert)):
            # Check if it is a call to print
            if isinstance(stmt, ast.Call) and isinstance(stmt.func, ast.Name):
                if stmt.func.id == "print":
                    continue
            has_substance = True

    return not has_raise and not has_substance


def check_swallowed_exceptions(tree: ast.AST) -> list[tuple[int, str]]:
    """Identify exception blocks that catch exceptions without raising or logging.

    Args:
        tree: The AST of the code.

    Returns:
        List of findings.
    """
    findings: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                # Catching general Exception or bare except:
                is_general = False
                if handler.type is None:
                    is_general = True
                elif (
                    isinstance(handler.type, ast.Name)
                    and handler.type.id == "Exception"
                ):
                    is_general = True

                if not is_general:
                    continue

                if is_handler_swallowed(handler):
                    findings.append(
                        (
                            handler.lineno,
                            "Swallowed exception: General handler catches error "
                            "but does not raise or log properly.",
                        )
                    )

    return findings


def check_unnecessary_classes(tree: ast.AST) -> list[tuple[int, str]]:
    """Scan code for classes containing only one method.

    Args:
        tree: The AST of the code.

    Returns:
        List of findings.
    """
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
            methods_sans_init = [m for m in methods if m != "__init__"]
            if len(methods_sans_init) == 1:
                findings.append(
                    (
                        node.lineno,
                        f"Unnecessary abstraction: Class '{node.name}' "
                        f"contains only one functional method "
                        f"('{methods_sans_init[0]}').",
                    )
                )
    return findings


def is_trivial_delegation(node: ast.FunctionDef) -> str | None:
    """Check if the function trivially forwards parameters to another function.

    Args:
        node: The FunctionDef node.

    Returns:
        The name of the target function if it is a trivial delegation, else None.
    """
    if len(node.body) != 1:
        return None
    stmt = node.body[0]
    if not (isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call)):
        return None
    call = stmt.value
    if not isinstance(call.func, ast.Name):
        return None
    fn_args = [arg.arg for arg in node.args.args]
    call_args = [arg.id for arg in call.args if isinstance(arg, ast.Name)]
    if fn_args == call_args:
        return call.func.id
    return None


def check_trivial_delegations(tree: ast.AST) -> list[tuple[int, str]]:
    """Scan code for functions that trivially forward parameters.

    Args:
        tree: The AST of the code.

    Returns:
        List of findings.
    """
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            target = is_trivial_delegation(node)
            if target:
                findings.append(
                    (
                        node.lineno,
                        f"Trivial delegation: Function '{node.name}' "
                        f"only forwards arguments to '{target}'.",
                    )
                )
    return findings


def check_unnecessary_abstractions(tree: ast.AST) -> list[tuple[int, str]]:
    """Detect single-method classes or trivial wrapper functions.

    Args:
        tree: The AST of the code.

    Returns:
        List of findings.
    """
    return check_unnecessary_classes(tree) + check_trivial_delegations(tree)


def audit_test_function(node: ast.FunctionDef) -> tuple[int, bool]:
    """Verify assertions in a single test function.

    Args:
        node: The test function AST node.

    Returns:
        Tuple of (assert_count, has_trivial_assert).
    """
    assert_count = 0
    trivial_assert = False

    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Assert):
            assert_count += 1
            if isinstance(stmt.test, ast.Constant):
                if stmt.test.value is True:
                    trivial_assert = True
            elif isinstance(stmt.test, ast.Compare):
                if (
                    isinstance(stmt.test.left, ast.Constant)
                    and len(stmt.test.comparators) == 1
                    and isinstance(stmt.test.comparators[0], ast.Constant)
                ):
                    if stmt.test.left.value == stmt.test.comparators[0].value:
                        trivial_assert = True

        elif isinstance(stmt, ast.Call):
            if isinstance(stmt.func, ast.Attribute):
                if stmt.func.attr.startswith("assert") or "assert" in stmt.func.attr:
                    assert_count += 1

    return assert_count, trivial_assert


def check_non_verifying_tests(tree: ast.AST) -> list[tuple[int, str]]:
    """Scan test functions for lack of actual assert verifications.

    Args:
        tree: The AST of the code.

    Returns:
        List of findings.
    """
    findings: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            assert_count, trivial_assert = audit_test_function(node)
            if assert_count == 0:
                findings.append(
                    (
                        node.lineno,
                        f"Non-verifying test: Test '{node.name}' "
                        f"has zero assert statements.",
                    )
                )
            elif trivial_assert:
                findings.append(
                    (
                        node.lineno,
                        f"Trivial assert: Test '{node.name}' asserts a static value.",
                    )
                )

    return findings


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Scan code likely generated or modified by AI " "for common quality bugs."
        )
    )
    parser.add_argument("file", help="Path to the python file to scan.")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: Scanned file '{args.file}' does not exist.")
        sys.exit(1)

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except (SyntaxError, OSError) as err:
        print(f"Error reading or parsing file: {err}")
        sys.exit(1)

    lines = content.splitlines()

    # Collect all stages
    imports = check_fake_imports(tree, file_path)
    duplicates = check_duplicate_helpers(tree)
    placeholders = check_placeholder_comments(lines)
    exceptions = check_swallowed_exceptions(tree)
    abstractions = check_unnecessary_abstractions(tree)
    tests = check_non_verifying_tests(tree)

    all_findings = (
        imports + duplicates + placeholders + exceptions + abstractions + tests
    )

    print(f"🤖 Running AI Code Sanitizer on: {file_path.name}")
    print("=" * 60)

    def print_issues(name: str, issues: list[tuple[int, str]]) -> None:
        print(f"\n📁 Stage: {name}")
        if issues:
            for line_no, msg in sorted(issues, key=lambda x: x[0]):
                print(f"  [L{line_no}]: {msg}")
        else:
            print("  [✅] Clean.")

    print_issues("Fake Imports & Nonexistent APIs", imports)
    print_issues("Duplicate Helpers", duplicates)
    print_issues("AI Placeholder Comments", placeholders)
    print_issues("Swallowed Exceptions", exceptions)
    print_issues("Unnecessary Abstractions", abstractions)
    print_issues("Non-Verifying Tests", tests)

    print("\n" + "=" * 60)
    if all_findings:
        print(f"❌ AI Code Sanitizer finished. Total issues found: {len(all_findings)}")
        sys.exit(1)
    else:
        print("🎉 Code looks healthy! No obvious AI anti-patterns detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()

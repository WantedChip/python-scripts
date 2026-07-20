#!/usr/bin/env python3
"""Example Drift Checker.

Scans codebase declarations and compares them with Python code example blocks
extracted from Markdown documentation files to spot out-of-date APIs.
"""

import argparse
import ast
import os
import sys
from typing import Any, Dict, List, Tuple


class DeclarationScanner(ast.NodeVisitor):
    """AST scanner to index defined classes, functions, and args in source."""

    def __init__(self) -> None:
        self.definitions: Dict[str, Dict[str, Any]] = {}

    # pylint: disable=invalid-name
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        self.definitions[node.name] = {"type": "Class", "args": []}
        self.generic_visit(node)

    # pylint: disable=invalid-name
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        # Ignore private/special
        if not (node.name.startswith("__") and node.name.endswith("__")):
            args = [arg.arg for arg in node.args.args]
            self.definitions[node.name] = {"type": "Function/Method", "args": args}
        self.generic_visit(node)


class ExampleUsageScanner(ast.NodeVisitor):
    """AST scanner to extract function calls in example code blocks."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    # pylint: disable=invalid-name
    def visit_Call(self, node: ast.Call) -> None:
        """Visit function call."""
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr

        if name:
            num_args = len(node.args)
            keywords = [kw.arg for kw in node.keywords if kw.arg]
            self.calls.append(
                {
                    "name": name,
                    "line": node.lineno,
                    "num_args": num_args,
                    "keywords": keywords,
                }
            )
        self.generic_visit(node)


def index_source_apis(src_dir: str) -> Dict[str, Dict[str, Any]]:
    """Parse all source files recursively to build API declarations index."""
    scanner = DeclarationScanner()
    exclude_dirs = {".git", "venv", ".venv", "build", "dist", "__pycache__"}

    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        tree = ast.parse(fh.read(), filename=fpath)
                    scanner.visit(tree)
                except (SyntaxError, OSError):
                    pass
    return scanner.definitions


def extract_python_blocks(doc_path: str) -> List[Tuple[str, int]]:
    """Scan docs and extract Python code block lines with line numbers."""
    blocks: List[Tuple[str, int]] = []
    if not os.path.exists(doc_path):
        return blocks

    try:
        with open(doc_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return blocks

    in_block = False
    current_block: List[str] = []
    start_line = 0

    for idx, line in enumerate(lines, 1):
        if line.strip().startswith("```python") or line.strip().startswith("```py"):
            in_block = True
            current_block = []
            start_line = idx + 1
        elif line.strip().startswith("```") and in_block:
            in_block = False
            blocks.append(("".join(current_block), start_line))
        elif in_block:
            current_block.append(line)

    return blocks


# pylint: disable=too-many-locals,too-many-nested-blocks
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify API examples in markdown documentation against source code "
            "definitions."
        )
    )
    parser.add_argument(
        "--src",
        default=".",
        help="Source directory containing codebase (default: current directory).",
    )
    parser.add_argument(
        "--docs",
        default=".",
        help=(
            "Documentation folder containing markdown files (default: current "
            "directory)."
        ),
    )

    args = parser.parse_args()

    src_dir = os.path.abspath(args.src)
    docs_dir = os.path.abspath(args.docs)

    print("========================================================================")
    print("EXAMPLE DRIFT CHECKER: DOCUMENTATION LINTER")
    print("========================================================================")
    print(f"Codebase Source:  {src_dir}")
    print(f"Documentation:    {docs_dir}")
    print("Indexing codebase API signatures...")

    # Step 1: Index source code API signatures
    api_index = index_source_apis(src_dir)
    print(f"Indexed {len(api_index):,} declared classes and functions.")
    print("-" * 80)

    # Step 2: Traverse documentation files and lint python blocks
    exclude_dirs = {".git", "venv", ".venv", "build", "dist", "node_modules"}
    drifts = []

    for root, dirs, files in os.walk(docs_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith((".md", ".txt")):
                doc_path = os.path.abspath(os.path.join(root, f))
                blocks = extract_python_blocks(doc_path)

                for block_code, start_line in blocks:
                    try:
                        # Parse example block using AST
                        tree = ast.parse(block_code)
                        usage_scanner = ExampleUsageScanner()
                        usage_scanner.visit(tree)

                        # Compare usage against declarations
                        for call in usage_scanner.calls:
                            name = call["name"]
                            if name in api_index:
                                decl = api_index[name]
                                # Check named keyword arguments
                                for kw in call["keywords"]:
                                    if decl["args"] and kw not in decl["args"]:
                                        rel_path = os.path.relpath(doc_path, docs_dir)
                                        issue_msg = (
                                            f"Keyword argument '{kw}' does not exist "
                                            f"in source code definition args list: "
                                            f"{decl['args']}"
                                        )
                                        drifts.append(
                                            {
                                                "file": rel_path,
                                                "line": start_line + call["line"] - 1,
                                                "api": name,
                                                "issue": issue_msg,
                                            }
                                        )
                    except SyntaxError:
                        # Skip unparseable draft snippets
                        pass

    if not drifts:
        print(
            "\n[+] Success: All documented code block examples match current API "
            "signatures."
        )
        sys.exit(0)

    print(f"\n[!] Flagged {len(drifts)} API drift issues in documentation:")
    print("=" * 80)
    for idx, d in enumerate(drifts, 1):
        print(f"{idx}. File: {d['file']} (Line: {d['line']})")
        print(f"   API Symbol: {d['api']}")
        print(f"   Drift:      {d['issue']}")
        print("-" * 80)


if __name__ == "__main__":
    main()

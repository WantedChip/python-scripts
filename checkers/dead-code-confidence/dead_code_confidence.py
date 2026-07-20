#!/usr/bin/env python3
"""Dead Code Confidence.

Performs static analysis on Python files, building an index of declared classes
and functions, then scans code files for references to score their unused
probability with evidence support.
"""

import argparse
import ast
import os
import re
import sys
from typing import Any, Dict, List, Tuple


class SymbolVisitor(ast.NodeVisitor):
    """AST visitor to extract declarations from a Python file."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.symbols: List[Dict[str, Any]] = []

    # pylint: disable=invalid-name
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Record class definition."""
        self.symbols.append(
            {
                "name": node.name,
                "type": "Class",
                "line": node.lineno,
                "file": self.file_path,
            }
        )
        self.generic_visit(node)

    # pylint: disable=invalid-name
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Record function definition."""
        # Ignore private/special methods like __init__
        if not (node.name.startswith("__") and node.name.endswith("__")):
            self.symbols.append(
                {
                    "name": node.name,
                    "type": "Function/Method",
                    "line": node.lineno,
                    "file": self.file_path,
                }
            )
        self.generic_visit(node)


def gather_declarations(target_dir: str) -> List[Dict[str, Any]]:
    """Parse all Python files in the directory recursively to extract declarations."""
    declarations = []
    exclude_dirs = {".git", "venv", ".venv", "build", "dist", "__pycache__"}

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.abspath(os.path.join(root, f))
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        tree = ast.parse(fh.read(), filename=fpath)
                    visitor = SymbolVisitor(fpath)
                    visitor.visit(tree)
                    declarations.extend(visitor.symbols)
                except (SyntaxError, OSError):
                    pass
    return declarations


def calculate_confidence(
    decl: Dict[str, Any], occurrences: Dict[str, List[Tuple[str, int]]]
) -> Tuple[int, List[str]]:
    """Analyze occurrences of a symbol to determine dead code confidence."""
    name = decl["name"]
    decl_file = decl["file"]
    decl_line = decl["line"]

    refs = occurrences.get(name, [])

    # Filter out reference if it matches the declaration coordinate itself
    clean_refs = []
    for ref_file, ref_line in refs:
        if ref_file == decl_file and ref_line == decl_line:
            continue
        clean_refs.append((ref_file, ref_line))

    # Heuristic Checks
    reasons = []
    if not clean_refs:
        reasons.append(
            "Symbol is never referenced anywhere in the directory outside its "
            "declaration."
        )
        return 99, reasons

    # Check if only referenced in test files
    in_production_code = False
    test_references = []

    for ref_file, ref_line in clean_refs:
        base_name = os.path.basename(ref_file)
        if (
            base_name.startswith("test_")
            or "_test.py" in base_name
            or "tests" in ref_file
        ):
            test_references.append((ref_file, ref_line))
        else:
            in_production_code = True

    if not in_production_code:
        reasons.append(
            f"Symbol is only referenced in test files ({len(test_references)} times)."
        )
        return 90, reasons

    # If it is referenced in production code, confidence is 0%
    return 0, []


# pylint: disable=too-many-locals,too-many-branches
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Verify unused functions and classes with confidence evidence logs."
    )
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=".",
        help="Folder to scan recursively (default: current directory).",
    )
    parser.add_argument(
        "-c",
        "--confidence",
        type=int,
        default=50,
        help="Minimum confidence threshold percentage to report (default: 50).",
    )

    args = parser.parse_args()

    target_dir = os.path.abspath(args.target_dir)
    if not os.path.exists(target_dir):
        print(f"Error: Path does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("DEAD CODE CONFIDENCE DETECTOR")
    print("========================================================================")
    print(f"Scanning directory: {target_dir}")
    print("Extracting code definitions and mapping references...")
    print("-" * 80)

    # Step 1: Gather declarations
    decls = gather_declarations(target_dir)
    if not decls:
        print("[-] No python class or function declarations found.", file=sys.stderr)
        sys.exit(0)

    # Step 2: Index all text occurrences of declared names (Fast global regex sweep)
    # Map: name -> list of (file, line_num)
    occurrences: Dict[str, List[Tuple[str, int]]] = {d["name"]: [] for d in decls}
    declared_names = set(occurrences.keys())

    # Build regex to search for declared names as whole words
    exclude_dirs = {".git", "venv", ".venv", "build", "dist", "__pycache__"}
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.abspath(os.path.join(root, f))
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        for line_num, line in enumerate(fh, 1):
                            # Find all words in line
                            words = re.findall(r"\b[a-zA-Z0-9_]+\b", line)
                            for w in words:
                                if w in declared_names:
                                    occurrences[w].append((fpath, line_num))
                except OSError:
                    pass

    # Step 3: Run diagnostics
    dead_candidates = []
    for d in decls:
        conf, reasons = calculate_confidence(d, occurrences)
        if conf >= args.confidence:
            dead_candidates.append(
                {
                    "name": d["name"],
                    "type": d["type"],
                    "file": d["file"],
                    "line": d["line"],
                    "confidence": conf,
                    "reasons": reasons,
                }
            )

    if not dead_candidates:
        print(
            f"\n[+] Success: No dead code candidates discovered above "
            f"{args.confidence}% confidence."
        )
        sys.exit(0)

    # Sort candidates by confidence (descending)
    dead_candidates.sort(key=lambda x: x["confidence"], reverse=True)

    print(f"\nDiscovered {len(dead_candidates)} dead code candidates:")
    print("=" * 80)
    for idx, c in enumerate(dead_candidates, 1):
        rel_path = os.path.relpath(c["file"], target_dir)
        print(f"{idx}. {c['type']}: {c['name']} (Confidence: {c['confidence']}% Stale)")
        print(f"   Location:  {rel_path}:{c['line']}")
        print("   Evidence Log:")
        for reason in c["reasons"]:
            print(f"     - {reason}")
        print("-" * 80)


if __name__ == "__main__":
    main()

"""Dependency Why Tool.

Explains why a Python package is installed by determining its dependency chain,
identifying which project components import it, and analyzing the impact of removing it.
"""

# pylint: disable=duplicate-code

import argparse
import ast
import json
import logging
import sys
from importlib.metadata import PackageNotFoundError, distributions, requires
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def get_all_installed_packages() -> Dict[str, Set[str]]:
    """Build a mapping of package_name -> set of required dependency names.

    Returns:
        Dictionary mapping package name to set of required packages.
    """
    pkg_deps: Dict[str, Set[str]] = {}
    for dist in distributions():
        name = dist.metadata["Name"].lower()
        reqs: Set[str] = set()
        raw_requires = requires(dist.metadata["Name"]) or []
        for req_str in raw_requires:
            # Strip extras and version specifiers
            clean_req = req_str.split(";")[0].split("(")[0].split()[0]
            base_req = clean_req.strip().lower()
            if base_req:
                reqs.add(base_req)
        pkg_deps[name] = reqs
    return pkg_deps


def find_dependency_chains(
    target_package: str, pkg_deps: Dict[str, Set[str]]
) -> List[List[str]]:
    """Find all dependency paths leading to target_package.

    Args:
        target_package: Target package name.
        pkg_deps: Mapping of package -> set of child requirements.

    Returns:
        List of dependency chain lists.
    """
    target = target_package.lower()
    dependents = [parent for parent, children in pkg_deps.items() if target in children]

    chains: List[List[str]] = []
    for parent in dependents:
        chains.append([parent, target])

    return chains


class ImportVisitor(ast.NodeVisitor):
    """AST visitor to extract imported package names and line numbers."""

    def __init__(self, target_package: str) -> None:
        """Initialize visitor for target package.

        Args:
            target_package: Target package name to search for.
        """
        self.target = target_package.lower().replace("-", "_")
        self.found_imports: List[Tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:  # pylint: disable=invalid-name
        """Visit AST Import node."""
        for alias in node.names:
            base_module = alias.name.split(".")[0].lower()
            if base_module == self.target:
                self.found_imports.append((node.lineno, alias.name))
        self.generic_visit(node)

    def visit_ImportFrom(  # pylint: disable=invalid-name
        self, node: ast.ImportFrom
    ) -> None:
        """Visit AST ImportFrom node."""
        if node.module:
            base_module = node.module.split(".")[0].lower()
            if base_module == self.target:
                self.found_imports.append((node.lineno, node.module))
        self.generic_visit(node)


def scan_codebase_imports(
    project_root: str, target_package: str
) -> Dict[str, List[Tuple[int, str]]]:
    """Scan Python files in codebase for imports of target_package.

    Args:
        project_root: Path to codebase root directory.
        target_package: Package name to search for.

    Returns:
        Dictionary mapping relative file path to list of (lineno, imported_symbol).
    """
    root = Path(project_root).resolve()
    usage_map: Dict[str, List[Tuple[int, str]]] = {}

    for py_file in root.rglob("*.py"):
        if ".venv" in py_file.parts or "venv" in py_file.parts:
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_file))
            visitor = ImportVisitor(target_package)
            visitor.visit(tree)
            if visitor.found_imports:
                rel_path = str(py_file.relative_to(root))
                usage_map[rel_path] = visitor.found_imports
        except SyntaxError:
            continue

    return usage_map


def analyze_dependency_why(
    target_package: str,
    project_root: str = ".",
    mock_pkg_deps: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, Any]:
    """Perform complete 'why is this package installed' analysis.

    Args:
        target_package: Target package name.
        project_root: Codebase root directory.
        mock_pkg_deps: Optional pre-built dependency map for testing.

    Returns:
        Analysis summary dictionary.
    """
    pkg_name = target_package.lower().strip()
    if mock_pkg_deps is not None:
        pkg_deps = mock_pkg_deps
    else:
        pkg_deps = get_all_installed_packages()

    is_installed = pkg_name in pkg_deps or any(p.lower() == pkg_name for p in pkg_deps)

    dep_chains = find_dependency_chains(pkg_name, pkg_deps)
    code_usage = scan_codebase_imports(project_root, pkg_name)
    code_usage_count = sum(len(locs) for locs in code_usage.values())

    consequences: List[str] = []

    if code_usage:
        files_str = ", ".join(list(code_usage.keys())[:3])
        msg = f"Codebase breakage: imported in {len(code_usage)} file(s) ({files_str})."
        consequences.append(msg)

    if dep_chains:
        parents = [c[0] for c in dep_chains]
        msg = (
            f"Package dependency breakage: required by "
            f"{len(parents)} package(s) ({', '.join(parents[:3])})."
        )
        consequences.append(msg)

    if not code_usage and not dep_chains:
        msg = "Safe to remove: no codebase imports or dependencies found."
        consequences.append(msg)

    return {
        "target_package": target_package,
        "is_installed": is_installed,
        "dependency_chains": dep_chains,
        "imported_in_codebase": bool(code_usage),
        "code_usage_summary": code_usage,
        "code_import_count": code_usage_count,
        "consequences_of_removal": consequences,
    }


def render_text_report(report: Dict[str, Any]) -> str:
    """Format analysis report as readable terminal text.

    Args:
        report: Dictionary containing analysis results.

    Returns:
        Formatted string output.
    """
    status_str = (
        "Installed" if report["is_installed"] else "Not Installed in environment"
    )
    lines = [
        f"=== Dependency Why Report for '{report['target_package']}' ===",
        f"Status: {status_str}",
        "",
        "--- Dependency Chains ---",
    ]

    chains = report.get("dependency_chains", [])
    if not chains:
        lines.append("No parent packages require this as a transitive dependency.")
    else:
        for chain in chains:
            lines.append(" -> ".join(chain))

    lines.append("")
    lines.append("--- Codebase Usage ---")
    code_usage = report.get("code_usage_summary", {})
    if not code_usage:
        lines.append("No imports found in project Python source files.")
    else:
        for file_path, imports in code_usage.items():
            lines.append(f"File: {file_path}")
            for line_no, sym in imports:
                lines.append(f"  Line {line_no}: import {sym}")

    lines.append("")
    lines.append("--- Removal Impact Analysis ---")
    for cons in report.get("consequences_of_removal", []):
        lines.append(f" - {cons}")

    return "\n".join(lines)


def setup_cli() -> argparse.ArgumentParser:
    """Setup CLI argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="Explain why a Python package is installed."
    )
    parser.add_argument(
        "--package",
        required=True,
        help="Name of the target Python package to analyze.",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Path to project codebase root directory (default: .).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: text or json (default: text).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def main() -> None:
    """CLI entrypoint function for dependency-why."""
    parser = setup_cli()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    try:
        report = analyze_dependency_why(
            target_package=args.package, project_root=args.project_root
        )

        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print(render_text_report(report))

    except PackageNotFoundError as exc:
        logging.error("Package not found: %s", exc)
        sys.exit(1)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.error("Analysis failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

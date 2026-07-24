"""Dependency Change Impact Tool.

Scans Python AST to identify imports, function calls, class usage,
and attribute accesses that may be impacted by upgrading a target dependency.
"""

# pylint: disable=duplicate-code

import argparse
import ast
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class ImpactLocation:
    """Represents a code call site or import impacted by dependency change."""

    file_path: str
    line_number: int
    expression: str
    risk_level: str  # HIGH, MEDIUM, LOW
    reason: str


class DependencyImpactVisitor(ast.NodeVisitor):
    """AST visitor to find package usage and breaking API call sites."""

    def __init__(
        self,
        target_package: str,
        deprecated_apis: Set[str],
        file_path: str,
    ) -> None:
        """Initialize visitor with target package and deprecated APIs.

        Args:
            target_package: Target package name (e.g. 'pydantic').
            deprecated_apis: Set of deprecated or changed API names.
            file_path: Relative path of file being scanned.
        """
        self.target = target_package.lower().replace("-", "_")
        self.deprecated_apis = {api.lower() for api in deprecated_apis}
        self.file_path = file_path
        self.imported_aliases: Set[str] = set()
        self.imported_symbols: Dict[str, str] = {}  # symbol -> orig_name
        self.impacts: List[ImpactLocation] = []

    def visit_Import(self, node: ast.Import) -> None:  # pylint: disable=invalid-name
        """Visit AST Import node."""
        for alias in node.names:
            base_mod = alias.name.split(".")[0].lower()
            if base_mod == self.target:
                alias_name = alias.asname or alias.name
                self.imported_aliases.add(alias_name)
                self.impacts.append(
                    ImpactLocation(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        expression=f"import {alias.name}",
                        risk_level="LOW",
                        reason=(f"Top-level import of target package '{self.target}'."),
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(  # pylint: disable=invalid-name
        self, node: ast.ImportFrom
    ) -> None:
        """Visit AST ImportFrom node."""
        if node.module:
            base_mod = node.module.split(".")[0].lower()
            if base_mod == self.target:
                for alias in node.names:
                    sym_name = alias.asname or alias.name
                    self.imported_symbols[sym_name] = alias.name
                    risk = (
                        "HIGH"
                        if alias.name.lower() in self.deprecated_apis
                        else "MEDIUM"
                    )
                    reason = (
                        f"Imported deprecated/changed API '{alias.name}'."
                        if risk == "HIGH"
                        else (
                            f"Imported symbol '{alias.name}' " f"from '{self.target}'."
                        )
                    )
                    self.impacts.append(
                        ImpactLocation(
                            file_path=self.file_path,
                            line_number=node.lineno,
                            expression=(f"from {node.module} import {alias.name}"),
                            risk_level=risk,
                            reason=reason,
                        )
                    )
        self.generic_visit(node)

    def visit_Attribute(  # pylint: disable=invalid-name
        self, node: ast.Attribute
    ) -> None:
        """Visit AST Attribute access node (e.g. pkg.api)."""
        if isinstance(node.value, ast.Name):
            if node.value.id in self.imported_aliases:
                attr_name = node.attr
                risk = "HIGH" if attr_name.lower() in self.deprecated_apis else "MEDIUM"
                reason = (
                    f"Accessing deprecated/changed attribute '{attr_name}'."
                    if risk == "HIGH"
                    else f"Attribute access on '{self.target}' alias."
                )
                self.impacts.append(
                    ImpactLocation(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        expression=f"{node.value.id}.{attr_name}",
                        risk_level=risk,
                        reason=reason,
                    )
                )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # pylint: disable=invalid-name
        """Visit AST Name usage node (e.g. using imported symbol)."""
        if node.id in self.imported_symbols and isinstance(node.ctx, ast.Load):
            orig_name = self.imported_symbols[node.id]
            if orig_name.lower() in self.deprecated_apis:
                self.impacts.append(
                    ImpactLocation(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        expression=node.id,
                        risk_level="HIGH",
                        reason=f"Usage site of deprecated API '{orig_name}'.",
                    )
                )
        self.generic_visit(node)


def scan_impacted_codebase(
    project_root: str,
    target_package: str,
    deprecated_apis: Set[str],
) -> List[ImpactLocation]:
    """Scan all Python files in project_root for dependency impact.

    Args:
        project_root: Path to codebase root.
        target_package: Target package name.
        deprecated_apis: Set of deprecated or changed API names.

    Returns:
        List of ImpactLocation instances sorted by risk level (HIGH first).
    """
    root = Path(project_root).resolve()
    all_impacts: List[ImpactLocation] = []

    for py_file in root.rglob("*.py"):
        if ".venv" in py_file.parts or "venv" in py_file.parts:
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_file))
            rel_path = str(py_file.relative_to(root))
            visitor = DependencyImpactVisitor(
                target_package=target_package,
                deprecated_apis=deprecated_apis,
                file_path=rel_path,
            )
            visitor.visit(tree)
            all_impacts.extend(visitor.impacts)
        except SyntaxError:
            continue

    # Sort HIGH risk first, then line number
    risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(
        all_impacts,
        key=lambda loc: (
            risk_order.get(loc.risk_level, 3),
            loc.file_path,
            loc.line_number,
        ),
    )


def load_deprecated_rules(rules_file: Optional[str]) -> Set[str]:
    """Load deprecated API names from a JSON rules file.

    Args:
        rules_file: Optional path to rules JSON file.

    Returns:
        Set of deprecated API name strings.
    """
    if not rules_file or not Path(rules_file).is_file():
        return set()

    try:
        content = Path(rules_file).read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, list):
            return {str(item) for item in data}
        if isinstance(data, dict) and "deprecated_apis" in data:
            return {str(item) for item in data["deprecated_apis"]}
    except Exception as exc:  # pylint: disable=broad-exception-caught # nosec B110
        logging.debug("Could not parse rules file %s: %s", rules_file, exc)
    return set()


def analyze_dependency_change_impact(
    target_package: str,
    project_root: str = ".",
    deprecated_apis: Optional[Set[str]] = None,
    rules_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyze code impact for a target dependency upgrade.

    Args:
        target_package: Target package name.
        project_root: Codebase root directory.
        deprecated_apis: Optional set of deprecated APIs.
        rules_file: Optional path to JSON rules file.

    Returns:
        Dictionary containing impact summary.
    """
    dep_apis = deprecated_apis or set()
    if rules_file:
        dep_apis = dep_apis.union(load_deprecated_rules(rules_file))

    impacts = scan_impacted_codebase(
        project_root=project_root,
        target_package=target_package,
        deprecated_apis=dep_apis,
    )

    high_risk_count = sum(1 for imp in impacts if imp.risk_level == "HIGH")
    medium_risk_count = sum(1 for imp in impacts if imp.risk_level == "MEDIUM")
    low_risk_count = sum(1 for imp in impacts if imp.risk_level == "LOW")

    return {
        "target_package": target_package,
        "project_root": str(Path(project_root).resolve()),
        "deprecated_apis_checked": list(dep_apis),
        "total_impact_sites": len(impacts),
        "risk_breakdown": {
            "HIGH": high_risk_count,
            "MEDIUM": medium_risk_count,
            "LOW": low_risk_count,
        },
        "impacts": [asdict(imp) for imp in impacts],
    }


def render_text_report(report: Dict[str, Any]) -> str:
    """Format impact report as readable text.

    Args:
        report: Analysis results dictionary.

    Returns:
        Formatted terminal text string.
    """
    title = (
        f"=== Dependency Change Impact Report for " f"'{report['target_package']}' ==="
    )
    lines = [
        title,
        f"Project Root: {report['project_root']}",
        f"Total Impact Sites Found: {report['total_impact_sites']}",
        (
            f"Risk Breakdown: HIGH={report['risk_breakdown']['HIGH']}, "
            f"MEDIUM={report['risk_breakdown']['MEDIUM']}, "
            f"LOW={report['risk_breakdown']['LOW']}"
        ),
        "",
        "--- Affected Code Locations ---",
    ]

    impacts = report.get("impacts", [])
    if not impacts:
        lines.append("No import or API usage sites found for this package.")
    else:
        for idx, imp in enumerate(impacts, 1):
            line_str = (
                f"{idx}. [{imp['risk_level']}] {imp['file_path']}:"
                f"{imp['line_number']} -> {imp['expression']}"
            )
            lines.append(line_str)
            lines.append(f"   Reason: {imp['reason']}")

    return "\n".join(lines)


def setup_cli() -> argparse.ArgumentParser:
    """Configure command line argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Find imports and APIs in your codebase affected before "
            "upgrading a dependency."
        )
    )
    parser.add_argument(
        "--package",
        required=True,
        help="Name of target Python dependency (e.g. pydantic, sqlalchemy).",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Path to project codebase root (default: current directory).",
    )
    parser.add_argument(
        "--api",
        action="append",
        default=[],
        help="Deprecated/changed API name (can be repeated).",
    )
    parser.add_argument(
        "--rules-file",
        help="Path to JSON rules file containing deprecated_apis list.",
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
    """CLI entrypoint function for dependency-change-impact."""
    parser = setup_cli()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    try:
        report = analyze_dependency_change_impact(
            target_package=args.package,
            project_root=args.project_root,
            deprecated_apis=set(args.api),
            rules_file=args.rules_file,
        )

        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print(render_text_report(report))

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.error("Impact analysis failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

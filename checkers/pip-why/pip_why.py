"""pip-why: Audits python environment packages and dependency paths.

Allows answering:
- Why is a package installed?
- Which dependency pulled it in?
- Can I safely remove it?
- Why are two versions conflicting?
"""

import argparse
import importlib.metadata
import json
import re
import sys
from typing import Dict, List, Optional, Set, Tuple


def normalize_name(name: str) -> str:
    """Normalize a package name per PEP 503.

    Args:
        name: Raw package name.

    Returns:
        Normalized package name.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirement(req_str: str) -> Optional[Tuple[str, str]]:
    """Parse a PEP 508 requirement string to extract name and specifiers.

    Args:
        req_str: Raw requirement string (e.g. 'requests (>=2.28.0) ; extra == "socks"').

    Returns:
        A tuple of (normalized_dependency_name, specifier_string), or None.
    """
    # Split out environment markers
    parts = req_str.split(";", 1)
    req_part = parts[0].strip()

    # Extract name using pattern matching
    match = re.match(r"^([a-zA-Z0-9_.-]+)", req_part)
    if not match:
        return None
    dep_name = match.group(1)
    name_len = len(dep_name)
    spec_part = req_part[name_len:].strip()

    # Verify that any remaining text starts with a valid requirement character
    if spec_part and not spec_part.startswith(("(", "<", ">", "=", "~", "!")):
        return None

    return normalize_name(dep_name), spec_part.strip("()")


def parse_version(ver_str: str) -> Tuple[int, ...]:
    """Parse a version string into a tuple of integers for comparison.

    Args:
        ver_str: Raw version string (e.g. '2.28.0.post1').

    Returns:
        Tuple of integer parts.
    """
    parts = []
    for part in re.findall(r"\d+", ver_str):
        parts.append(int(part))
    return tuple(parts)


def parse_specifiers(spec_str: str) -> List[Tuple[str, Tuple[int, ...]]]:
    """Parse specifier string (e.g., '>=2.28.0, <3.0') into constraints list.

    Args:
        spec_str: The specifier string from requirement.

    Returns:
        List of tuples of (operator, parsed_version_tuple).
    """
    constraints = []
    for constraint in spec_str.split(","):
        constraint = constraint.strip()
        if not constraint:
            continue
        match = re.match(r"^(>=|<=|==|!=|~=|>|<)?\s*(.*)$", constraint)
        if match:
            op, val = match.groups()
            op = op or "=="
            # Extract just digits and dots for parsing version tuple
            val_clean = re.match(r"^([0-9.]+)", val)
            val_str = val_clean.group(1) if val_clean else val
            constraints.append((op, parse_version(val_str)))
    return constraints


def match_constraint(
    installed_ver: Tuple[int, ...], op: str, required_ver: Tuple[int, ...]
) -> bool:
    # pylint: disable=too-many-return-statements
    """Check if an installed version tuple satisfies a single operator constraint.

    Args:
        installed_ver: Parsed version of installed package.
        op: Constraint operator (e.g. '>=', '==').
        required_ver: Parsed required version constraint.

    Returns:
        True if satisfied, False otherwise.
    """
    if op == "==":
        min_len = min(len(installed_ver), len(required_ver))
        return installed_ver[:min_len] == required_ver[:min_len]
    if op == "!=":
        min_len = min(len(installed_ver), len(required_ver))
        return installed_ver[:min_len] != required_ver[:min_len]
    if op == ">=":
        return installed_ver >= required_ver
    if op == "<=":
        return installed_ver <= required_ver
    if op == ">":
        return installed_ver > required_ver
    if op == "<":
        return installed_ver < required_ver
    if op == "~=":
        if len(required_ver) < 2:
            return installed_ver >= required_ver
        upper_limit = list(required_ver[:-1])
        upper_limit[-1] += 1
        return required_ver <= installed_ver < tuple(upper_limit)
    return True


class DependencyGraph:
    """Dependency graph representation of the current Python environment."""

    def __init__(self) -> None:
        """Initialize empty graph structures."""
        self.packages: Dict[str, str] = {}  # name -> version
        self.dependencies: Dict[str, List[Tuple[str, str]]] = (
            {}
        )  # name -> [(dep, spec)]
        self.dependents: Dict[str, List[str]] = {}  # dep -> [names]

    def load_environment(self) -> None:
        """Load packages and requirements from the active environment."""
        # First pass: map all installed packages
        for dist in importlib.metadata.distributions():
            raw_name = dist.metadata.get("Name")
            if not raw_name:
                continue
            name = normalize_name(raw_name)
            self.packages[name] = dist.version
            self.dependencies[name] = []

        # Second pass: link dependencies (only checking installed packages)
        for dist in importlib.metadata.distributions():
            raw_name = dist.metadata.get("Name")
            if not raw_name:
                continue
            name = normalize_name(raw_name)
            requires = dist.requires
            if requires:
                for req_str in requires:
                    parsed = parse_requirement(req_str)
                    if parsed:
                        dep_name, spec = parsed
                        if dep_name in self.packages:
                            self.dependencies[name].append((dep_name, spec))
                            self.dependents.setdefault(dep_name, []).append(name)

    def find_all_paths(
        self, start: str, target: str, path: List[str], visited: Set[str]
    ) -> List[List[str]]:
        """Find all paths from start node to target node recursively.

        Args:
            start: Current package name in path.
            target: Target package name.
            path: Path accumulated so far.
            visited: Set of visited nodes to avoid cycles.

        Returns:
            List of package name paths from start to target.
        """
        if start == target:
            return [path + [target]]

        visited.add(start)
        paths = []
        for dep, _ in self.dependencies.get(start, []):
            if dep not in visited:
                paths.extend(self.find_all_paths(dep, target, path + [start], visited))
        visited.remove(start)
        return paths

    def get_why_paths(self, target: str) -> List[List[str]]:
        """Get all dependency paths from top-level packages to target.

        Args:
            target: Target package name.

        Returns:
            List of dependency paths.
        """
        target = normalize_name(target)
        if target not in self.packages:
            return []

        # Top-level packages have no dependents in the active environment
        top_levels = [pkg for pkg in self.packages if pkg not in self.dependents]

        all_paths = []
        for start in top_levels:
            all_paths.extend(self.find_all_paths(start, target, [], set()))
        return all_paths

    def check_safe_remove(self, target: str) -> Tuple[bool, List[str]]:
        """Determine if a package can be safely uninstalled.

        Args:
            target: Target package name.

        Returns:
            A tuple of (is_safe, list_of_dependent_packages).
        """
        target = normalize_name(target)
        if target not in self.packages:
            return True, []

        deps = self.dependents.get(target, [])
        return len(deps) == 0, sorted(list(set(deps)))

    def check_conflicts(self) -> List[Tuple[str, str, str, str, str]]:
        """Scan all installed packages to detect version conflicts.

        Returns:
            List of (package, pkg_version, dep, dep_installed_version, spec).
        """
        conflicts = []
        for pkg, deps in self.dependencies.items():
            for dep, spec in deps:
                installed_ver = self.packages.get(dep)
                if installed_ver:
                    constraints = parse_specifiers(spec)
                    parsed_installed = parse_version(installed_ver)
                    satisfied = True
                    for op, req_ver in constraints:
                        if not match_constraint(parsed_installed, op, req_ver):
                            satisfied = False
                            break
                    if not satisfied:
                        conflicts.append(
                            (
                                pkg,
                                self.packages[pkg],
                                dep,
                                installed_ver,
                                spec,
                            )
                        )
        return conflicts


def render_paths(paths: List[List[str]]) -> None:
    """Print paths in a readable format.

    Args:
        paths: List of package paths.
    """
    if not paths:
        print("No dependency paths found.")
        return

    print(f"Found {len(paths)} path(s):")
    for idx, path in enumerate(paths, 1):
        print(f"  {idx}. " + " -> ".join(path))


def main() -> None:
    # pylint: disable=too-many-branches,too-many-locals,too-many-statements
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Explain why Python packages are installed in the environment."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: why
    why_parser = subparsers.add_parser(
        "why", help="Explain why a package is installed."
    )
    why_parser.add_argument("package", help="Name of the package to query.")
    why_parser.add_argument(
        "--json", action="store_true", help="Output in JSON format."
    )

    # Subcommand: remove-check
    remove_parser = subparsers.add_parser(
        "remove-check", help="Check if a package can be safely uninstalled."
    )
    remove_parser.add_argument("package", help="Name of the package to check.")
    remove_parser.add_argument(
        "--json", action="store_true", help="Output in JSON format."
    )

    # Subcommand: conflicts
    conflicts_parser = subparsers.add_parser(
        "conflicts", help="Scan the environment for dependency conflicts."
    )
    conflicts_parser.add_argument(
        "--json", action="store_true", help="Output in JSON format."
    )

    args = parser.parse_args()

    graph = DependencyGraph()
    graph.load_environment()

    if args.command == "why":
        package = normalize_name(args.package)
        if package not in graph.packages:
            print(f"Error: Package '{args.package}' is not installed.")
            sys.exit(1)

        paths = graph.get_why_paths(package)
        if args.json:
            print(json.dumps({"package": package, "paths": paths}, indent=2))
        else:
            print(
                f"Package '{package}' (version {graph.packages[package]}) is installed."
            )
            render_paths(paths)

    elif args.command == "remove-check":
        package = normalize_name(args.package)
        if package not in graph.packages:
            print(f"Package '{args.package}' is not installed.")
            sys.exit(0)

        safe, dependents = graph.check_safe_remove(package)
        if args.json:
            print(
                json.dumps(
                    {
                        "package": package,
                        "safe_to_remove": safe,
                        "dependents": dependents,
                    },
                    indent=2,
                )
            )
            if not safe:
                sys.exit(1)
        else:
            if safe:
                print(f"Yes, '{package}' can be safely removed (0 active dependents).")
            else:
                print(
                    f"No, '{package}' cannot be safely removed. "
                    "The following packages depend on it:"
                )
                for dep in dependents:
                    print(f"  - {dep}")
                sys.exit(1)

    elif args.command == "conflicts":
        conflicts = graph.check_conflicts()
        if args.json:
            out = []
            for pkg, pkg_ver, dep, dep_ver, spec in conflicts:
                out.append(
                    {
                        "package": pkg,
                        "version": pkg_ver,
                        "dependency": dep,
                        "installed_version": dep_ver,
                        "required_specifier": spec,
                    }
                )
            print(json.dumps(out, indent=2))
            if conflicts:
                sys.exit(1)
        else:
            if not conflicts:
                print("No dependency conflicts detected in the environment.")
            else:
                print(f"Detected {len(conflicts)} version conflict(s):")
                for pkg, pkg_ver, dep, dep_ver, spec in conflicts:
                    print(
                        f"  - {pkg} (version {pkg_ver}) requires {dep} ({spec}), "
                        f"but {dep} (version {dep_ver}) is installed."
                    )
                sys.exit(1)


if __name__ == "__main__":
    main()

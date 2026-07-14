#!/usr/bin/env python3
"""Works On My Machine.

Inspects a Python project to audit execution reproducibility. Verifies Python
version constraints, OS assumptions, environment variables, external binaries,
ports, package versions, and undeclared system dependencies.
"""

import argparse
import ast
import importlib.metadata
import importlib.util
import os
import re
import shutil
import socket
import sys
from pathlib import Path
from typing import Optional


def check_python_version(project_dir: Path) -> list[str]:
    """Audit project python version constraints.

    Args:
        project_dir: Root directory of the project.

    Returns:
        List of findings.
    """
    findings: list[str] = []
    current_version = f"{sys.version_info.major}.{sys.version_info.minor}"

    # Search for version constraint files
    pyproject = project_dir / "pyproject.toml"
    python_ver_file = project_dir / ".python-version"

    if python_ver_file.exists():
        try:
            ver = python_ver_file.read_text(encoding="utf-8").strip()
            if not current_version.startswith(ver) and ver not in current_version:
                findings.append(
                    f"Python version mismatch: .python-version requests '{ver}', "
                    f"but running on '{sys.version}'"
                )
        except OSError:
            pass

    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
            # Simple regex search to avoid toml dependency
            match = re.search(r"requires-python\s*=\s*\"([^\"]+)\"", content)
            if match:
                req = match.group(1)
                findings.extend(evaluate_version_constraint(req, current_version))
        except OSError:
            pass

    return findings


def evaluate_version_constraint(constraint: str, current_version: str) -> list[str]:
    """Helper to evaluate version strings like >=3.8.

    Args:
        constraint: The constraint string.
        current_version: The running python version.

    Returns:
        List of findings if invalid.
    """
    findings: list[str] = []
    # Match >=3.8, >3.8, ==3.8 etc.
    match = re.match(r"([>=<!~]+)\s*([\d\.]+)", constraint.strip())
    if match:
        op, ver = match.groups()
        curr_tuple = tuple(map(int, current_version.split(".")))
        ver_tuple = tuple(map(int, ver.split(".")))

        # Fill tuples to same length
        max_len = max(len(curr_tuple), len(ver_tuple))
        curr_tuple += (0,) * (max_len - len(curr_tuple))
        ver_tuple += (0,) * (max_len - len(ver_tuple))

        is_valid = True
        if op == ">=" and curr_tuple < ver_tuple:
            is_valid = False
        elif op == "==" and curr_tuple != ver_tuple:
            is_valid = False
        elif op == ">" and curr_tuple <= ver_tuple:
            is_valid = False

        if not is_valid:
            findings.append(
                f"Python version constraint unsatisfied: Requires '{constraint}', "
                f"but currently running on '{current_version}'"
            )
    return findings


def check_os_assumptions(tree: ast.AST) -> list[str]:
    """Check for hardcoded platform assumptions or imports.

    Args:
        tree: The AST of the project files combined.

    Returns:
        List of findings.
    """
    findings: list[str] = []
    platform_locked_modules = {"winreg", "msvcrt", "pwd", "grp", "termios", "fcntl"}

    for node in ast.walk(tree):
        # 1. Platform-locked modules
        if isinstance(node, ast.Import):
            for name in node.names:
                if name.name in platform_locked_modules:
                    findings.append(
                        f"Line {node.lineno}: Import of platform-specific "
                        f"module '{name.name}'"
                    )
        elif (
            isinstance(node, ast.ImportFrom) and node.module in platform_locked_modules
        ):
            findings.append(
                f"Line {node.lineno}: Import from platform-specific "
                f"module '{node.module}'"
            )

        # 2. Hardcoded absolute paths
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            # Windows drive path or unix root absolute path
            if (
                re.match(r"^[C-Z]:\\", val)
                or val.startswith("/usr/")
                or val.startswith("/var/")
            ):
                findings.append(
                    f"Line {node.lineno}: Hardcoded absolute path reference: '{val}'"
                )

    return findings


def get_environment_vars(tree: ast.AST) -> list[tuple[int, str]]:
    """Scan AST for environment variable lookups.

    Args:
        tree: The AST of the project files.

    Returns:
        List of tuples (line_no, env_var_name).
    """
    vars_found: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # os.environ.get('KEY') or os.getenv('KEY')
            is_env = False
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id == "os" and node.func.attr == "getenv":
                    is_env = True
                elif node.func.value.id == "environ" and node.func.attr == "get":
                    is_env = True
            elif (
                isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "os"
                and node.func.value.attr == "environ"
                and node.func.attr == "get"
            ):
                is_env = True

            if is_env and node.args and isinstance(node.args[0], ast.Constant):
                vars_found.append((node.lineno, str(node.args[0].value)))

        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            # os.environ['KEY']
            if (
                isinstance(node.value.value, ast.Name)
                and node.value.value.id == "os"
                and node.value.attr == "environ"
                and isinstance(node.slice, ast.Constant)
            ):
                vars_found.append((node.lineno, str(node.slice.value)))

    return vars_found


def check_missing_env_vars(tree: ast.AST) -> list[str]:
    """Audit project environment variables.

    Args:
        tree: The AST of the code.

    Returns:
        List of findings.
    """
    findings: list[str] = []
    vars_found = get_environment_vars(tree)

    for line_no, var_name in vars_found:
        if var_name not in os.environ:
            findings.append(
                f"Line {line_no}: Environment variable '{var_name}' is referenced "
                "but missing from current environment."
            )

    return findings


def get_subprocess_calls(tree: ast.AST) -> list[tuple[int, str]]:
    """Scan AST for external binary command targets.

    Args:
        tree: The AST of the project.

    Returns:
        List of tuples (line_no, binary_name).
    """
    calls: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            is_sub = False
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
            ):
                if node.func.attr in {"run", "Popen", "call", "check_output"}:
                    is_sub = True
            elif (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "system"
            ):
                # os.system('binary')
                if node.args and isinstance(node.args[0], ast.Constant):
                    cmd_str = str(node.args[0].value).split()[0]
                    calls.append((node.lineno, cmd_str))
                continue

            if is_sub and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.List) and arg0.elts:
                    if isinstance(arg0.elts[0], ast.Constant):
                        calls.append((node.lineno, str(arg0.elts[0].value)))
                elif isinstance(arg0, ast.Constant):
                    # string command e.g. "ffmpeg -i input"
                    cmd_str = str(arg0.value).split()[0]
                    calls.append((node.lineno, cmd_str))

    return list(set(calls))


def check_missing_binaries(tree: ast.AST) -> list[str]:
    """Audit system binary dependency reachability.

    Args:
        tree: The AST of the code.

    Returns:
        List of findings.
    """
    findings: list[str] = []
    calls = get_subprocess_calls(tree)

    for line_no, binary in calls:
        # Ignore python scripts running other python scripts
        if binary.endswith(".py") or binary == "python" or binary == "python3":
            continue
        if not shutil.which(binary):
            findings.append(
                f"Line {line_no}: External binary '{binary}' is invoked "
                "but not found on system PATH."
            )

    return findings


def get_ports_from_code(tree: ast.AST) -> list[tuple[int, int]]:
    """Scan AST for hardcoded port assignments.

    Args:
        tree: The AST.

    Returns:
        List of tuples (line_no, port_number).
    """
    ports: list[tuple[int, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.upper() in {
                    "PORT",
                    "CONN_PORT",
                }:
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, int
                    ):
                        ports.append((node.lineno, node.value.value))

    return list(set(ports))


def check_ports(tree: ast.AST) -> list[str]:
    """Check if ports referenced in code are listening or blocked.

    Args:
        tree: The AST of the project.

    Returns:
        List of findings.
    """
    findings: list[str] = []
    ports = get_ports_from_code(tree)

    for line_no, port in ports:
        # Try to bind to port locally to verify if it is blocked
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            findings.append(
                f"Line {line_no}: Port {port} is referenced in code "
                f"but currently blocked or in use."
            )
        finally:
            sock.close()

    return findings


def parse_requirements(requirements_file: Path) -> dict[str, str]:
    """Parse declared requirements file into package map.

    Args:
        requirements_file: Path to requirements.txt.

    Returns:
        Dictionary mapping package name to constraint.
    """
    packages: dict[str, str] = {}
    if not requirements_file.exists():
        return packages

    try:
        content = requirements_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Match package name and optional constraint
            match = re.match(r"^([a-zA-Z0-9_\-]+)(.*)$", line)
            if match:
                pkg, constraint = match.groups()
                packages[pkg.lower().replace("-", "_")] = constraint.strip()
    except OSError:
        pass

    return packages


def check_package_versions(project_dir: Path) -> list[str]:
    """Verify if declared dependencies are installed and versions match.

    Args:
        project_dir: Root directory of the project.

    Returns:
        List of findings.
    """
    findings: list[str] = []
    req_file = project_dir / "requirements.txt"
    if not req_file.exists():
        return findings

    packages = parse_requirements(req_file)

    for pkg, constraint in packages.items():
        try:
            installed_ver = importlib.metadata.version(pkg.replace("_", "-"))
            if constraint.startswith("=="):
                expected_ver = constraint[2:].strip()
                if installed_ver != expected_ver:
                    findings.append(
                        f"Package '{pkg}' version mismatch: Requires '{expected_ver}', "
                        f"but '{installed_ver}' is installed."
                    )
        except importlib.metadata.PackageNotFoundError:
            findings.append(
                f"Required package '{pkg}' is declared in requirements.txt "
                "but not installed in the environment."
            )

    return findings


def check_undeclared_dependencies(tree: ast.AST, project_dir: Path) -> list[str]:
    """Verify if third-party modules imported in code are declared in requirements.

    Args:
        tree: The AST.
        project_dir: The project root directory.

    Returns:
        List of findings.
    """
    findings: list[str] = []
    req_file = project_dir / "requirements.txt"
    declared_pkgs = parse_requirements(req_file) if req_file.exists() else {}

    # Safe built-in standard library package names to ignore
    stdlib_modules = sys.builtin_module_names

    imported_pkgs: set[tuple[int, str]] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imported_pkgs.add((node.lineno, name.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                imported_pkgs.add((node.lineno, node.module.split(".")[0]))

    for line_no, pkg in imported_pkgs:
        pkg_lower = pkg.lower().replace("-", "_")
        # Ignore stdlib, local packages, or self imports
        if pkg_lower in stdlib_modules or pkg_lower == "sys" or pkg_lower == "os":
            continue
        # Verify if it is standard library via importlib spec
        try:
            spec = importlib.util.find_spec(pkg)
            if spec is not None:
                # Check origin spec to distinguish stdlib vs site-packages
                origin = spec.origin or ""
                if "site-packages" not in origin and "dist-packages" not in origin:
                    continue
        except Exception:  # pylint: disable=broad-exception-caught  # nosec B110
            pass

        # Check if local relative directory or file exists (local import)
        if (
            project_dir.joinpath(f"{pkg}.py").exists()
            or project_dir.joinpath(pkg).is_dir()
        ):
            continue

        if pkg_lower not in declared_pkgs:
            findings.append(
                f"Line {line_no}: Imported package '{pkg}' is a third-party module "
                "but not declared in requirements.txt."
            )

    return findings


def scan_directory_ast(project_dir: Path) -> Optional[ast.AST]:
    """Parse all python files in project directory and merge into a single AST.

    Args:
        project_dir: Root directory of project.

    Returns:
        Merged AST, or None if no python files exist.
    """
    combined_body: list[ast.stmt] = []

    for file in project_dir.rglob("*.py"):
        # Skip hidden files or virtual environments
        if ".venv" in file.parts or ".git" in file.parts or "tests" in file.parts:
            continue
        try:
            content = file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            combined_body.extend(tree.body)
        except (SyntaxError, OSError):
            pass

    if not combined_body:
        return None

    return ast.Module(body=combined_body, type_ignores=[])


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect Python project and generate execution " "reproducibility report."
        )
    )
    parser.add_argument("directory", help="Root directory of the project to inspect.")
    args = parser.parse_args()

    project_dir = Path(args.directory).resolve()
    if not project_dir.is_dir():
        print(f"Error: Inspect target '{args.directory}' is not a directory.")
        sys.exit(1)

    print(f"🔍 Inspecting Python project for reproducibility: {project_dir.name}")
    print("=" * 60)

    # 1. Python constraints
    py_findings = check_python_version(project_dir)

    # Compile AST of files
    tree = scan_directory_ast(project_dir)
    if tree is None:
        print("Warning: No python source files found in target directory.")
        tree = ast.Module(body=[], type_ignores=[])

    # 2. Audits
    os_findings = check_os_assumptions(tree)
    env_findings = check_missing_env_vars(tree)
    binary_findings = check_missing_binaries(tree)
    port_findings = check_ports(tree)
    package_findings = check_package_versions(project_dir)
    undeclared_findings = check_undeclared_dependencies(tree, project_dir)

    total_issues = (
        len(py_findings)
        + len(os_findings)
        + len(env_findings)
        + len(binary_findings)
        + len(port_findings)
        + len(package_findings)
        + len(undeclared_findings)
    )

    def print_section(title: str, items: list[str]) -> None:
        print(f"\n📋 Audit Stage: {title}")
        if items:
            for item in items:
                print(f"  [⚠️] {item}")
        else:
            print("  [✅] No issues detected.")

    print_section("Python Version Constraints", py_findings)
    print_section("OS/Platform Assumptions", os_findings)
    print_section("Missing Environment Variables", env_findings)
    print_section("Missing System Binaries", binary_findings)
    print_section("Port Constraints & Availability", port_findings)
    print_section("Package Versions & Installed Match", package_findings)
    print_section("Undeclared Dependencies", undeclared_findings)

    print("\n" + "=" * 60)
    if total_issues:
        print(
            f"❌ Inspections finished. Total reproducibility bugs flagged: "
            f"{total_issues}"
        )
        sys.exit(1)
    else:
        print(
            "🎉 Code looks fully reproducible! No obvious host "
            "dependency risks identified."
        )
        sys.exit(0)


if __name__ == "__main__":
    main()

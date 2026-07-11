"""Dependency Update Reporter.

A utility to scan Python projects for outdated packages, check PyPI for updates,
evaluate breaking-version upgrade risks (SemVer check), and list changelogs.
"""

import argparse
import json
import logging
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

# Python 3.11+ standard library tomllib for pyproject.toml
if sys.version_info >= (3, 11):
    import tomllib
else:
    # Fallback dictionary parser for pyproject.toml in older python versions
    tomllib = None  # type: ignore # pylint: disable=invalid-name


# pylint: disable=duplicate-code

logger = logging.getLogger("dep_reporter")


@dataclass
class DependencyReport:
    """Represents a scanned dependency check report."""

    name: str
    required_version: str
    latest_version: str
    latest_release_date: str
    upgrade_risk: str  # High, Medium, Low, None
    changelog_url: str
    error: Optional[str] = None


def setup_logging(verbose: bool) -> None:
    """Configure logger settings."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def parse_semver(ver_str: str) -> Tuple[int, int, int]:
    """Parse version string into major, minor, patch integers.

    Args:
        ver_str: version string (e.g. '1.2.3', 'v2.0.0b1')

    Returns:
        Tuple of (major, minor, patch).
    """
    cleaned = re.sub(r"^[vV]", "", ver_str.strip())
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", cleaned)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else 0
        patch = int(match.group(3)) if match.group(3) else 0
        return major, minor, patch
    return 0, 0, 0


def evaluate_upgrade_risk(req: str, latest: str) -> str:
    """Compare version parts to calculate breaking upgrade risk.

    Args:
        req: required/installed version string.
        latest: latest available version string from PyPI.

    Returns:
        Risk level string: 'High', 'Medium', 'Low', or 'None'.
    """
    if not req or req == "latest" or req == "*":
        return "None"

    req_maj, req_min, req_pat = parse_semver(req)
    lat_maj, lat_min, lat_pat = parse_semver(latest)

    if lat_maj > req_maj:
        return "High (Major version mismatch)"
    if lat_min > req_min:
        return "Medium (Minor version mismatch)"
    if lat_pat > req_pat:
        return "Low (Patch update available)"

    return "None"


def parse_requirements_txt(content: str) -> Dict[str, str]:
    """Parse requirements.txt file contents.

    Args:
        content: string text of requirements.txt.

    Returns:
        Dictionary mapping package name to pinned version (if any).
    """
    deps = {}
    lines = content.split("\n")
    for line in lines:
        line_strip = line.strip()
        if not line_strip or line_strip.startswith("#") or line_strip.startswith("-r"):
            continue

        # Match package name and version pins
        # Supports ==, >=, <=, ~=, >, <
        match = re.match(
            r"^([a-zA-Z0-9_\-\[\]]+)\s*([>=<~!]+)\s*([a-zA-Z0-9_\-\.]+)", line_strip
        )
        if match:
            pkg = match.group(1).lower()
            ver = match.group(3)
            deps[pkg] = ver
        else:
            # Unpinned package e.g. 'numpy'
            pkg_name = re.match(r"^([a-zA-Z0-9_\-\[\]]+)", line_strip)
            if pkg_name:
                deps[pkg_name.group(1).lower()] = "*"

    return deps


def parse_pyproject_toml(content: str) -> Dict[str, str]:
    """Parse dependencies from pyproject.toml.

    Args:
        content: pyproject.toml string content.

    Returns:
        Dictionary of package dependencies mapping.
    """
    # pylint: disable=too-many-locals, too-many-branches, too-many-nested-blocks
    deps: Dict[str, str] = {}

    if tomllib is None:
        # Fallback regex parser for older Python versions
        for match in re.finditer(
            r'^([a-zA-Z0-9_\-]+)\s*=\s*"([^"]+)"', content, re.MULTILINE
        ):
            deps[match.group(1).lower()] = match.group(2)
        return deps

    try:
        data = tomllib.loads(content)
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to parse TOML structure: %s", err)
        return deps

    # 1. PEP 621 Standard project dependencies
    project = data.get("project", {})
    if isinstance(project, dict):
        # dependencies list e.g. ["pypdf>=6.0", "requests==2.31.0"]
        prod_deps = project.get("dependencies", [])
        if isinstance(prod_deps, list):
            for d in prod_deps:
                match = re.match(
                    r"^([a-zA-Z0-9_\-]+)\s*([>=<~!]+)\s*([a-zA-Z0-9_\-\.]+)", d
                )
                if match:
                    deps[match.group(1).lower()] = match.group(3)
                else:
                    pkg_name = re.match(r"^([a-zA-Z0-9_\-]+)", d)
                    if pkg_name:
                        deps[pkg_name.group(1).lower()] = "*"

    # 2. Poetry tool dependencies
    tool = data.get("tool", {})
    if isinstance(tool, dict):
        poetry = tool.get("poetry", {})
        if isinstance(poetry, dict):
            # Production dependencies
            po_deps = poetry.get("dependencies", {})
            if isinstance(po_deps, dict):
                for pkg, val in po_deps.items():
                    if pkg.lower() == "python":
                        continue
                    if isinstance(val, str):
                        deps[pkg.lower()] = val
                    elif isinstance(val, dict):
                        deps[pkg.lower()] = val.get("version", "*")

            # Dev dependency group
            group = poetry.get("group", {})
            if isinstance(group, dict):
                for _, g_info in group.items():
                    if isinstance(g_info, dict):
                        g_deps = g_info.get("dependencies", {})
                        if isinstance(g_deps, dict):
                            for pkg, val in g_deps.items():
                                if isinstance(val, str):
                                    deps[pkg.lower()] = val

    return deps


def fetch_pypi_metadata(package_name: str) -> Dict[str, Any]:
    """Fetch package metadata from PyPI JSON endpoint.

    Args:
        package_name: Target package name.

    Returns:
        JSON response parsed as dictionary.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    req = urllib.request.Request(
        url, headers={"User-Agent": "AntigravityDepReporter/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310

            return cast(Dict[str, Any], json.loads(resp.read().decode("utf-8")))

    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise ValueError(f"Package not found on PyPI: {package_name}") from err
        raise
    except Exception as err:
        raise ConnectionError(f"Network error querying PyPI: {err}") from err


def find_changelog(info: Dict[str, Any]) -> str:
    """Locate release changelog link inside package project_urls dictionary.

    Args:
        info: PyPI info metadata payload.

    Returns:
        String URL of the changelog or homepage.
    """
    urls = info.get("project_urls") or {}
    for name, url in urls.items():
        name_lower = name.lower()
        if any(
            keyword in name_lower
            for keyword in ["changelog", "release notes", "history", "changes"]
        ):
            return str(url)

    # Fallback to homepage or PyPI page
    return str(urls.get("Homepage") or info.get("project_url") or "")


def fetch_latest_release_date(releases: Dict[str, Any], latest_version: str) -> str:
    """Fetch release publication date from PyPI metadata.

    Args:
        releases: PyPI releases dictionary.
        latest_version: Target latest version string.

    Returns:
        Formatted date string.
    """
    pkg_releases = releases.get(latest_version) or []
    if pkg_releases:
        upload_time = pkg_releases[0].get("upload_time")
        if upload_time:
            # Extract date part: YYYY-MM-DD
            return str(upload_time.split("T")[0])
    return "N/A"


def scan_dependencies(deps: Dict[str, str]) -> List[DependencyReport]:
    """Query PyPI and compile reports for each dependency.

    Args:
        deps: package mapping from parsed files.

    Returns:
        List of DependencyReport entries.
    """
    reports = []
    logger.info("Scanning %d dependencies...", len(deps))

    for pkg, req_ver in deps.items():
        logger.debug("Fetching metadata for %s...", pkg)
        try:
            metadata = fetch_pypi_metadata(pkg)
            info = metadata.get("info") or {}
            latest_version = info.get("version") or "N/A"
            changelog_url = find_changelog(info)
            releases = metadata.get("releases") or {}
            release_date = fetch_latest_release_date(releases, latest_version)

            risk = evaluate_upgrade_risk(req_ver, latest_version)

            reports.append(
                DependencyReport(
                    name=pkg,
                    required_version=req_ver,
                    latest_version=latest_version,
                    latest_release_date=release_date,
                    upgrade_risk=risk,
                    changelog_url=changelog_url,
                )
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.warning("Error scanning package %s: %s", pkg, err)

            reports.append(
                DependencyReport(
                    name=pkg,
                    required_version=req_ver,
                    latest_version="N/A",
                    latest_release_date="N/A",
                    upgrade_risk="None",
                    changelog_url="N/A",
                    error=str(err),
                )
            )

    return reports


def print_markdown_report(reports: List[DependencyReport]) -> str:
    """Format dependency reports as Markdown tables."""
    lines = [
        "# Dependency Update Report\n",
        "| Package | Required | Latest | Released | Upgrade Risk | Changelog Link |",
        "|---|---|---|---|---|---|",
    ]
    for r in reports:
        risk_str = r.upgrade_risk
        if r.error:
            risk_str = f"Error: {r.error}"
        changelog = f"[Link]({r.changelog_url})" if r.changelog_url != "N/A" else "N/A"
        lines.append(
            f"| **{r.name}** | `{r.required_version}` | "
            f"`{r.latest_version}` | {r.latest_release_date} | "
            f"{risk_str} | {changelog} |"
        )

    return "\n".join(lines) + "\n"


def print_terminal_report(reports: List[DependencyReport]) -> None:
    """Print dependency reports in pretty terminal layout."""
    sys.stdout.write("\n=== Outdated Dependencies Audit Report ===\n\n")
    # Formatting widths
    header_fmt = "{:<20} {:<12} {:<12} {:<12} {:<25} {}\n"
    sys.stdout.write(
        header_fmt.format(
            "Package", "Required", "Latest", "Released", "Upgrade Risk", "Changelog"
        )
    )
    sys.stdout.write("-" * 95 + "\n")

    for r in reports:
        risk_str = r.upgrade_risk
        if r.error:
            risk_str = "Scan Error"
        sys.stdout.write(
            header_fmt.format(
                r.name,
                r.required_version,
                r.latest_version,
                r.latest_release_date,
                risk_str,
                r.changelog_url,
            )
        )
    sys.stdout.write("\n==========================================\n")


def main() -> None:
    """CLI execution entry point."""
    # pylint: disable=too-many-branches, too-many-statements
    parser = argparse.ArgumentParser(
        description=(
            "Dependency Update Reporter — audit requirements.txt "
            "or pyproject.toml for PyPI updates."
        )
    )

    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        help="Path to dependency file (defaults to scanning current directory).",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output report file path.")
    parser.add_argument(
        "--format",
        choices=["terminal", "markdown", "json"],
        default="terminal",
        help="Report formatting style (default: terminal).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # 1. Locate file
    file_path = args.input
    if not file_path:
        # Try local directory search for requirements.txt or pyproject.toml
        req_txt = Path("requirements.txt")
        pyproj = Path("pyproject.toml")
        if req_txt.exists():
            file_path = req_txt
        elif pyproj.exists():
            file_path = pyproj
        else:
            logger.error(
                "No requirements.txt or pyproject.toml found in "
                "current directory. Specify --input."
            )
            sys.exit(1)

    if not file_path.exists():
        logger.error("Dependency file not found: %s", file_path.as_posix())
        sys.exit(1)

    logger.info("Scanning dependency file: %s", file_path.name)
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to read file %s: %s", file_path.name, err)
        sys.exit(1)

    # 2. Parse file
    if file_path.suffix.lower() == ".toml":
        deps = parse_pyproject_toml(content)
    else:
        deps = parse_requirements_txt(content)

    if not deps:
        logger.warning("No dependencies found to scan.")
        sys.exit(0)

    # 3. Query PyPI and run audit
    reports = scan_dependencies(deps)

    # 4. Handle output formats
    if args.output:
        suffix = args.output.suffix.lower()
        try:
            if suffix == ".json":
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump([asdict(r) for r in reports], f, indent=2)
            elif suffix in [".md", ".markdown"]:
                md_content = print_markdown_report(reports)
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(md_content)
            else:
                # Default to saving terminal audit layout
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write("=== Outdated Dependencies Audit Report ===\n\n")
                    for r in reports:
                        f.write(f"Package: {r.name}\n")
                        f.write(
                            f"  Required: {r.required_version} | "
                            f"Latest: {r.latest_version}\n"
                        )
                        f.write(
                            f"  Risk: {r.upgrade_risk} | "
                            f"Changelog: {r.changelog_url}\n\n"
                        )
            logger.info("Audit report written to: %s", args.output.as_posix())
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.error("Failed to save audit report: %s", err)
            sys.exit(1)
    else:
        # Standard stdout prints
        if args.format == "terminal":
            print_terminal_report(reports)
        elif args.format == "markdown":
            sys.stdout.write(print_markdown_report(reports))
        elif args.format == "json":
            sys.stdout.write(json.dumps([asdict(r) for r in reports], indent=2))


if __name__ == "__main__":
    main()

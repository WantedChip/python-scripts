#!/usr/bin/env python3
"""Dependency Risk Report.

Audits requirements.txt for outdated packages, queries PyPI to identify version
gaps, lists Python dependencies, and scores SemVer upgrade risk metrics.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def parse_requirements_txt(file_path: str) -> List[Tuple[str, str]]:
    """Parse requirements.txt file and extract package names and pinned versions."""
    packages: List[Tuple[str, str]] = []
    if not os.path.exists(file_path):
        return packages

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_strip = line.strip()
                if (
                    not line_strip
                    or line_strip.startswith("#")
                    or line_strip.startswith("-")
                ):
                    continue

                # Split on comparison operators: ==, >=, <=, ~=, >, <
                parts = re.split(r"==|>=|<=|~=|==|!=|>|<", line_strip)
                if parts:
                    pkg_name = parts[0].strip()
                    # Skip local directory packages or URL packages
                    if pkg_name.startswith(".") or "/" in pkg_name or "@" in pkg_name:
                        continue

                    pkg_ver = ""
                    if len(parts) > 1:
                        # Extract the version digits/characters
                        pkg_ver = parts[1].split(";")[0].strip()

                    packages.append((pkg_name, pkg_ver))
    except OSError:
        pass
    return packages


def query_pypi_package(pkg_name: str) -> Optional[Dict[str, Any]]:
    """Fetch package metadata from PyPI JSON API endpoint."""
    url = f"https://pypi.org/pypi/{pkg_name}/json"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "DependencyRiskReport/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3.0) as response:  # nosec B310
            res: Dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return res
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None


def calculate_upgrade_risk(local_ver: str, latest_ver: str) -> Tuple[str, str]:
    """Determine upgrade risk based on SemVer versions difference."""
    if not local_ver or not latest_ver:
        return "Unknown", "Missing version specifications to assess risk"

    if local_ver == latest_ver:
        return "None", "Up to date"

    # Split version strings into components
    local_parts = local_ver.split(".")
    latest_parts = latest_ver.split(".")

    try:
        local_major = (
            int(local_parts[0]) if local_parts and local_parts[0].isdigit() else 0
        )
        latest_major = (
            int(latest_parts[0]) if latest_parts and latest_parts[0].isdigit() else 0
        )

        if latest_major > local_major:
            return (
                "High",
                f"Major version bump ({local_ver} -> {latest_ver}). "
                "Breaking changes and API re-writes likely.",
            )

        local_minor = (
            int(local_parts[1])
            if len(local_parts) > 1 and local_parts[1].isdigit()
            else 0
        )
        latest_minor = (
            int(latest_parts[1])
            if len(latest_parts) > 1 and latest_parts[1].isdigit()
            else 0
        )

        if latest_minor > local_minor:
            return (
                "Medium",
                f"Minor version bump ({local_ver} -> {latest_ver}). "
                "New features, minor deprecation risks.",
            )

        return (
            "Low",
            f"Patch/bugfix update ({local_ver} -> {latest_ver}). Safe to upgrade.",
        )
    except (ValueError, KeyError, TypeError):
        return (
            "Low",
            f"Outdated version gap ({local_ver} -> {latest_ver}). SemVer unparseable.",
        )


# pylint: disable=too-many-locals
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Assess version gaps and SemVer upgrade risks in package dependencies."
        )
    )
    parser.add_argument(
        "requirements_file",
        nargs="?",
        default="requirements.txt",
        help="Path to requirements.txt file (default: requirements.txt).",
    )

    args = parser.parse_args()

    req_path = os.path.abspath(args.requirements_file)
    if not os.path.exists(req_path):
        print(f"Error: Requirements file does not exist: {req_path}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("DEPENDENCY RISK REPORT: UPGRADE RISK AUDITOR")
    print("========================================================================")
    print(f"File Audited: {req_path}")
    print("Connecting to PyPI registry api services...")
    print("-" * 80)

    packages = parse_requirements_txt(req_path)
    if not packages:
        print("[-] No packages parsed from requirements file.", file=sys.stderr)
        sys.exit(0)

    header_fmt = (
        f"{'PACKAGE':<22} | {'LOCAL':<10} | {'LATEST':<10} | {'RISK':<8} | "
        f"{'REASON / METADATA'}"
    )
    print(header_fmt)
    print("-" * 80)

    risk_counts = {"High": 0, "Medium": 0, "Low": 0, "None": 0, "Unknown": 0}

    for name, ver in packages:
        pypi_data = query_pypi_package(name)
        if not pypi_data:
            print(
                f"{name:<22} | {ver:<10} | {'N/A':<10} | {'Unknown':<8} | "
                "Registry request failed or package not found"
            )
            risk_counts["Unknown"] += 1
            continue

        info = pypi_data.get("info", {})
        latest_ver = info.get("version", "")
        py_req = info.get("requires_python", "Any")

        risk_lvl, risk_reason = calculate_upgrade_risk(ver, latest_ver)
        risk_counts[risk_lvl] += 1

        # Truncate explanation if too long
        if len(risk_reason) > 50:
            risk_reason = risk_reason[:47] + "..."

        # Output row details
        local_display = ver if ver else "Any"
        row_fmt = (
            f"{name:<22} | {local_display:<10} | {latest_ver:<10} | {risk_lvl:<8} | "
            f"{risk_reason} [Python: {py_req}]"
        )
        print(row_fmt)

    print("\n" + "=" * 80)
    print("RISK PROFILE SUMMARY:")
    print(f"  High Risk upgrades:   {risk_counts['High']}")
    print(f"  Medium Risk upgrades: {risk_counts['Medium']}")
    print(f"  Low Risk updates:     {risk_counts['Low']}")
    print(f"  Up-to-date packages:  {risk_counts['None']}")
    print(f"  Unknown packages:     {risk_counts['Unknown']}")
    print("=" * 80)


if __name__ == "__main__":
    main()

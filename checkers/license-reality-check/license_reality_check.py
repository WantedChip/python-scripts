#!/usr/bin/env python3
"""License Reality Check.

Scans dependencies (from requirements.txt) and maps their licenses against an
approved license policy to identify potential copyleft or compatibility issues.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import List, Tuple

# Approved open-source licenses list
APPROVED_LICENSES = [
    "mit",
    "bsd",
    "apache",
    "isc",
    "python",
    "unlicense",
    "cc0",
    "public domain",
    "simplified bsd",
    "new bsd",
    "freebsd",
    "w3c",
]

# Copyleft/restrictive licenses that require warning
RESTRICTIVE_LICENSES = ["gpl", "agpl", "lgpl", "mpl", "epl", "cddl", "gfdl"]


def parse_requirements_txt(file_path: str) -> List[str]:
    """Parse requirements.txt file and extract package names."""
    packages: List[str] = []
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

                parts = re.split(r"==|>=|<=|~=|==|!=|>|<", line_strip)
                if parts:
                    pkg_name = parts[0].strip()
                    if pkg_name.startswith(".") or "/" in pkg_name or "@" in pkg_name:
                        continue
                    packages.append(pkg_name)
    except OSError:
        pass
    return packages


def query_pypi_license(pkg_name: str) -> Tuple[str, str]:
    """Fetch package license information from PyPI JSON API."""
    url = f"https://pypi.org/pypi/{pkg_name}/json"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "LicenseRealityCheck/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3.0) as response:  # nosec B310
            data = json.loads(response.read().decode("utf-8"))
            info = data.get("info", {})

            # Extract license field
            lic = info.get("license", "").strip()
            # If empty or generic, check classifiers
            classifiers = info.get("classifiers", [])
            license_classifier = "Unknown"
            for c in classifiers:
                if c.startswith("License ::"):
                    license_classifier = c.split("::")[-1].strip()
                    break

            # Select the most descriptive
            if not lic or len(lic) > 100 or lic.lower() in ("osl Approved", "unknown"):
                lic = license_classifier
            return lic, info.get("home_page", "")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return "Unknown", ""


def evaluate_license_risk(license_name: str) -> Tuple[str, str]:
    """Analyze license safety against copyleft and permitted standards."""
    lic_lower = license_name.lower()

    if lic_lower == "unknown":
        return "Warning", "License details not found on PyPI"

    # Match restrictive copyleft
    for r_lic in RESTRICTIVE_LICENSES:
        if r_lic in lic_lower:
            return (
                "High Risk",
                f"Restrictive copyleft license ({license_name}). "
                "May require code disclosure.",
            )

    # Match approved permissive
    for a_lic in APPROVED_LICENSES:
        if a_lic in lic_lower:
            return "Permissive", "Permissive open-source license. Safe to distribute."

    return (
        "Needs Review",
        "Unclassified custom or hybrid license. Verify compatibility.",
    )


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Verify license compatibility of project package dependencies."
    )
    parser.add_argument(
        "requirements_file",
        nargs="?",
        default="requirements.txt",
        help="Path to requirements.txt (default: requirements.txt).",
    )

    args = parser.parse_args()

    req_path = os.path.abspath(args.requirements_file)
    if not os.path.exists(req_path):
        print(f"Error: Requirements file does not exist: {req_path}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("LICENSE REALITY CHECK: COMPLIANCE AUDITOR")
    print("========================================================================")
    print(f"File Audited: {req_path}")
    print("Querying PyPI license registry services...")
    print("-" * 80)

    packages = parse_requirements_txt(req_path)
    if not packages:
        print("[-] No packages found in requirements file.", file=sys.stderr)
        sys.exit(0)

    print(f"{'PACKAGE':<22} | {'LICENSE':<25} | {'RISK STATUS':<12} | {'DETAILS'}")
    print("-" * 80)

    risk_counts = {"Permissive": 0, "Needs Review": 0, "Warning": 0, "High Risk": 0}

    for name in packages:
        lic, _ = query_pypi_license(name)
        risk_lvl, risk_reason = evaluate_license_risk(lic)
        risk_counts[risk_lvl] += 1

        # Format license display
        lic_display = lic if len(lic) <= 25 else lic[:22] + "..."
        print(f"{name:<22} | {lic_display:<25} | {risk_lvl:<12} | {risk_reason}")

    print("\n" + "=" * 80)
    print("LICENSE AUDIT REPORT SUMMARY:")
    print(f"  Permissive Licenses: {risk_counts['Permissive']}")
    print(f"  Restrictive Copyleft: {risk_counts['High Risk']}")
    print(f"  Unclassified (Review): {risk_counts['Needs Review']}")
    print(f"  Missing License:     {risk_counts['Warning']}")
    print("=" * 80)


if __name__ == "__main__":
    main()

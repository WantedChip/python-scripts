#!/usr/bin/env python3
"""repo-doctor.

Scans repositories to detect health issues: missing README sections, broken setup files,
stale dependencies, missing gitignore entries, giant files, accidental binaries,
dead links, and suspicious secrets.
"""

import argparse
import ast
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# Try importing tomllib/tomli for pyproject.toml parsing
try:
    import tomllib  # type: ignore[import-not-found, unused-ignore]

    HAS_TOMLLIB = True
except ImportError:
    HAS_TOMLLIB = False


def check_readme(repo_path: Path) -> list[str]:
    """Verify README exists and check for standard sections.

    Args:
        repo_path: Path to the repository root.

    Returns:
        List of findings.
    """
    findings = []
    readme_candidates = [
        repo_path / "README.md",
        repo_path / "readme.md",
        repo_path / "README.txt",
        repo_path / "README",
    ]
    readme_file: Optional[Path] = None
    for candidate in readme_candidates:
        if candidate.exists():
            readme_file = candidate
            break

    if not readme_file:
        return ["Missing README file (e.g., README.md) at root."]

    try:
        content = readme_file.read_text(encoding="utf-8")
        required_headers = [
            (
                "Installation",
                re.compile(r"^(#+\s+.*install|#+\s+getting\s+started)", re.I | re.M),
            ),
            ("Usage", re.compile(r"^(#+\s+usage|#+\s+how\s+to\s+run)", re.I | re.M)),
            ("License", re.compile(r"^(#+\s+license|#+\s+licence)", re.I | re.M)),
            (
                "Requirements",
                re.compile(r"^(#+\s+require|#+\s+prereq|#+\s+depend)", re.I | re.M),
            ),
        ]
        for name, pattern in required_headers:
            if not pattern.search(content):
                findings.append(f"README is missing '{name}' section header.")
    except Exception as err:  # pylint: disable=broad-exception-caught
        findings.append(f"Error reading README file: {err}")

    return findings


def check_setup_files(repo_path: Path) -> list[str]:
    """Validate python setup metadata files.

    Args:
        repo_path: Path to the repository root.

    Returns:
        List of findings.
    """
    findings = []
    pyproject = repo_path / "pyproject.toml"
    setup_py = repo_path / "setup.py"

    if pyproject.exists():
        if HAS_TOMLLIB:
            try:
                with pyproject.open("rb") as f:
                    tomllib.load(f)
            except Exception as err:  # pylint: disable=broad-exception-caught
                findings.append(f"pyproject.toml has syntax errors: {err}")
        else:
            # Fallback syntax check using json or basic load if tomllib is missing
            try:
                content = pyproject.read_text(encoding="utf-8")
                # Basic bracket count check
                if content.count("[") != content.count("]"):
                    findings.append(
                        "pyproject.toml has mismatched brackets (basic check)."
                    )
            except Exception as err:  # pylint: disable=broad-exception-caught
                findings.append(f"Error reading pyproject.toml: {err}")

    if setup_py.exists():
        try:
            content = setup_py.read_text(encoding="utf-8")
            ast.parse(content)
        except SyntaxError as err:
            findings.append(f"setup.py has python syntax errors: {err}")
        except Exception as err:  # pylint: disable=broad-exception-caught
            findings.append(f"Error checking setup.py: {err}")

    return findings


def query_pypi_latest(package_name: str) -> Optional[str]:
    """Fetch latest package version from PyPI JSON API.

    Args:
        package_name: Name of python library.

    Returns:
        Version string or None if error/offline.
    """
    # Clean package name to handle extras e.g. pkg[extra]
    clean_name = re.split(r"[\[<>=!~]", package_name)[0].strip()
    url = f"https://pypi.org/pypi/{clean_name}/json"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "repo-doctor/1.0"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as response:  # nosec B310
            data = json.loads(response.read().decode("utf-8"))
            return str(data["info"]["version"])
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def check_stale_dependencies(repo_path: Path, check_pypi: bool = False) -> list[str]:
    """Scan requirements.txt and check for stale dependencies.

    Args:
        repo_path: Path to the repository root.
        check_pypi: Query PyPI for outdated packages.

    Returns:
        List of findings.
    """
    findings: list[str] = []
    req_file = repo_path / "requirements.txt"
    if not req_file.exists():
        return findings

    try:
        content = req_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Check if pinned
            if "==" in line:
                pkg, current_ver = line.split("==", 1)
                pkg = pkg.strip()
                current_ver = current_ver.strip()

                if check_pypi:
                    latest = query_pypi_latest(pkg)
                    if latest and latest != current_ver:
                        findings.append(
                            f"Dependency '{pkg}' is outdated "
                            f"(current: {current_ver}, latest: {latest})."
                        )
            else:
                # Not pinned
                findings.append(
                    f"Dependency '{line}' is not pinned to a specific version."
                )
    except Exception as err:  # pylint: disable=broad-exception-caught
        findings.append(f"Error auditing dependencies: {err}")

    return findings


def check_gitignore(repo_path: Path) -> list[str]:
    """Verify standard gitignore rules are present.

    Args:
        repo_path: Path to the repository root.

    Returns:
        List of findings.
    """
    findings = []
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists():
        return ["Missing .gitignore file."]

    try:
        content = gitignore.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines()]

        rules_to_check = [
            ("Python virtual environments", re.compile(r"(\.venv|venv|env/)")),
            ("Python bytecode cache", re.compile(r"(__pycache__|/\.pyc|\.pyo)")),
            ("Build distribution folder", re.compile(r"(build/|dist/|\.egg-info)")),
            ("IDE project configurations", re.compile(r"(\.vscode|\.idea)")),
            (
                "Testing coverage reports",
                re.compile(r"(\.htmlcov|\.coverage|\.pytest_cache)"),
            ),
        ]

        for desc, pattern in rules_to_check:
            matched = False
            for line in lines:
                if pattern.search(line):
                    matched = True
                    break
            if not matched:
                findings.append(f".gitignore is missing patterns for {desc}.")
    except Exception as err:  # pylint: disable=broad-exception-caught
        findings.append(f"Error reading .gitignore: {err}")

    return findings


def scan_file_system_issues(
    repo_path: Path, max_size_mb: int = 10
) -> tuple[list[str], list[str]]:
    """Crawls files to check for giant files and unignored binaries.

    Args:
        repo_path: Root repository directory.
        max_size_mb: Threshold limit.

    Returns:
        Tuple of (giant_files_findings, accidental_binaries_findings).
    """
    giant_findings = []
    binary_findings = []

    binary_extensions = {
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".pyc",
        ".o",
        ".a",
        ".class",
        ".jar",
        ".zip",
        ".tar.gz",
        ".tgz",
        ".rar",
    }

    exclude_dirs = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "build",
        "dist",
    }

    # Determine files that match git exclusions if any
    for root, dirs, files in os.walk(repo_path):
        # In-place modify dirs to skip excluded folders
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for f in files:
            f_path = Path(root) / f
            try:
                stat = f_path.stat()
                size_mb = stat.st_size / (1024 * 1024)
                if size_mb > max_size_mb:
                    giant_findings.append(
                        f"Giant file detected: "
                        f"{f_path.relative_to(repo_path).as_posix()} "
                        f"({size_mb:.2f} MB)"
                    )

                # Check for binary extension
                if f_path.suffix.lower() in binary_extensions:
                    binary_findings.append(
                        "Suspicious binary/archive file: "
                        f"{f_path.relative_to(repo_path).as_posix()}"
                    )
            except OSError:
                continue

    return giant_findings, binary_findings


def verify_url(url: str) -> bool:
    """Verify HTTP/HTTPS link is not broken.

    Args:
        url: target URL string.

    Returns:
        True if valid/reachable, False otherwise.
    """
    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "repo-doctor/1.0"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as response:  # nosec B310
            return int(response.status) < 400
    except urllib.error.HTTPError as err:
        # Fallback to GET check on 405 Method Not Allowed
        if err.code == 405:
            try:
                req_get = urllib.request.Request(
                    url,
                    method="GET",
                    headers={"User-Agent": "repo-doctor/1.0"},
                )
                with urllib.request.urlopen(
                    req_get, timeout=2.0
                ) as response_get:  # nosec B310
                    return int(response_get.status) < 400
            except Exception:  # pylint: disable=broad-exception-caught
                return False
        return False
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def check_dead_links(repo_path: Path) -> list[str]:
    # pylint: disable=too-many-locals
    """Scan markdown files for dead http links.

    Args:
        repo_path: Path to the repository root.

    Returns:
        List of findings.
    """
    findings = []
    # Find markdown files
    md_files = []
    exclude_dirs = {".git", ".venv", "venv", "node_modules", "build", "dist"}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(".md"):
                md_files.append(Path(root) / f)

    link_pattern = re.compile(r"https?://[^\s)\]#]+")

    checked_urls: dict[str, bool] = {}

    for md in md_files:
        try:
            content = md.read_text(encoding="utf-8")
            urls = link_pattern.findall(content)
            for url in set(urls):
                # Clean trailing periods, commas or punctuation
                clean_url = url.rstrip(".,;:")
                if clean_url not in checked_urls:
                    # Validate
                    is_ok = verify_url(clean_url)
                    checked_urls[clean_url] = is_ok

                if not checked_urls[clean_url]:
                    rel_path = md.relative_to(repo_path).as_posix()
                    findings.append(f"Dead link in {rel_path}: {clean_url}")
        except Exception as err:  # pylint: disable=broad-exception-caught
            findings.append(f"Error parsing links in {md}: {err}")

    return findings


def calculate_entropy(data: str) -> float:
    """Calculate Shannon entropy of a string.

    Args:
        data: The string value.

    Returns:
        The Shannon entropy score.
    """
    import math  # pylint: disable=import-outside-toplevel

    if not data:
        return 0.0
    entropy = 0.0
    for x in set(data):
        p_x = data.count(x) / len(data)
        entropy += -p_x * math.log2(p_x)
    return entropy


def check_secrets(repo_path: Path) -> list[str]:
    # pylint: disable=too-many-locals, too-many-nested-blocks
    """Scan text files for potential credentials and secret tokens.

    Args:
        repo_path: Path to the repository root.

    Returns:
        List of findings.
    """
    findings = []
    exclude_dirs = {".git", ".venv", "venv", "node_modules", "build", "dist"}
    text_suffixes = {
        ".py",
        ".json",
        ".yaml",
        ".yml",
        ".txt",
        ".md",
        ".ini",
        ".conf",
        ".env",
    }

    # Standard secret patterns
    patterns = [
        ("AWS Client Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("GitHub Token", re.compile(r"\bghp_[0-9a-zA-Z]{36}\b")),
        ("Private Key Header", re.compile(r"-----BEGIN\s+.*PRIVATE\s+KEY-----")),
        (
            "Generic Password Assignment",
            re.compile(
                r"\b(password|pass|passwd|secret|api_key|apikey|token)"
                r"\s*=\s*['\"][^'\"]{8,}['\"]",
                re.I,
            ),
        ),
    ]

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            f_path = Path(root) / f
            if f_path.suffix.lower() not in text_suffixes:
                continue

            try:
                content = f_path.read_text(encoding="utf-8", errors="ignore")
                # 1. Regex check
                for name, regex in patterns:
                    for match in regex.finditer(content):
                        # Filter out common dummy placeholders
                        val = match.group(0)
                        if (
                            "your_" in val.lower()
                            or "dummy" in val.lower()
                            or "example" in val.lower()
                        ):
                            continue
                        rel_path = f_path.relative_to(repo_path).as_posix()
                        findings.append(
                            f"Suspicious {name} in {rel_path} (value: {val[:20]}...)"
                        )

                # 2. Shannon high entropy string token check
                # Check lines for strings of high-entropy length >= 32
                for line_idx, line in enumerate(content.splitlines(), start=1):
                    for word in re.split(r"[\s'\"=:,;]+", line):
                        if len(word) >= 32 and re.match(r"^[A-Za-z0-9+/=_-]+$", word):
                            entropy = calculate_entropy(word)
                            if entropy > 4.5:
                                # Skip common hashes or known non-secrets
                                if re.match(r"^[0-9a-fA-F]{32,64}$", word):  # md5/sha
                                    continue
                                rel_path = f_path.relative_to(repo_path).as_posix()
                                findings.append(
                                    f"High-entropy token in {rel_path}:L{line_idx} "
                                    f"(entropy: {entropy:.2f}, prefix: {word[:10]}...)"
                                )
            except OSError:
                continue

    return findings


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="repo-doctor: Run repository diagnostics."
    )
    parser.add_argument(
        "dir",
        nargs="?",
        default=".",
        help="Repository root directory to scan (default: '.').",
    )
    parser.add_argument(
        "--check-pypi",
        action="store_true",
        help="Query PyPI API to audit for outdated dependencies (slower).",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=10,
        help="Threshold size in MB to flag giant files (default: 10).",
    )
    args = parser.parse_args()

    repo_path = Path(args.dir)
    if not repo_path.exists():
        print(f"Error: Path '{args.dir}' does not exist.")
        sys.exit(1)

    print(f"🏥 Running repo-doctor diagnostics on: {repo_path.resolve()}")
    print("=" * 60)

    # Run check stages
    readme_issues = check_readme(repo_path)
    setup_issues = check_setup_files(repo_path)
    stale_deps = check_stale_dependencies(repo_path, args.check_pypi)
    gitignore_issues = check_gitignore(repo_path)
    giant_files, binaries = scan_file_system_issues(repo_path, args.max_size)
    dead_links = check_dead_links(repo_path)
    secrets_findings = check_secrets(repo_path)

    all_findings = (
        readme_issues
        + setup_issues
        + stale_deps
        + gitignore_issues
        + giant_files
        + binaries
        + dead_links
        + secrets_findings
    )

    # Output formatting
    def print_stage(name: str, issues: list[str]) -> None:
        print(f"\n📁 Stage: {name}")
        if issues:
            for issue in issues:
                print(f"  [⚠️] {issue}")
        else:
            print("  [✅] No issues detected.")

    print_stage("README Verification", readme_issues)
    print_stage("Setup Configurations", setup_issues)
    print_stage("Dependencies & Pinning", stale_deps)
    print_stage(".gitignore Audit", gitignore_issues)
    print_stage("Giant Files", giant_files)
    print_stage("Suspicious Binaries / Archives", binaries)
    print_stage("Dead Documentation Links", dead_links)
    print_stage("Secret Leak Scanner", secrets_findings)

    print("\n" + "=" * 60)
    if all_findings:
        print(f"❌ repo-doctor finished. Total issues found: {len(all_findings)}")
        sys.exit(1)
    else:
        print("🎉 repo-doctor finished. Repository is in excellent health!")
        sys.exit(0)


if __name__ == "__main__":
    main()

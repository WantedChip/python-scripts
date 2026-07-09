#!/usr/bin/env python3
"""ENV Auditor.

Compares a .env file with .env.example, Docker Compose files, and source
code files to find:
  - Variables defined in .env but missing from .env.example (undocumented)
  - Variables in .env.example but missing from .env (missing locally)
  - Variables never referenced in source code (unused)
  - Variables used in source but not declared anywhere (unknown)

Secret values are NEVER printed.
"""

import argparse
import fnmatch
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_SOURCE_EXTS: Tuple[str, ...] = (
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rb",
    ".sh",
    ".php",
    ".java",
    ".kt",
    ".rs",
    ".cs",
    ".cpp",
    ".c",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".conf",
    ".ini",
    ".dockerfile",
    ".tf",
)
DOCKER_COMPOSE_PATTERNS: Tuple[str, ...] = (
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "compose*.yml",
    "compose*.yaml",
)

# Pattern to find env var references in source code
# Matches: os.environ['KEY'], os.getenv('KEY'), process.env.KEY, ${KEY}, $KEY etc.
VAR_USAGE_PATTERNS: List[re.Pattern[str]] = [
    # os.environ['KEY']  (bracket access)
    re.compile(r"""os\.environ\s*\[\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),
    # os.environ.get('KEY', ...) or os.environ.get("KEY")  (method call)
    re.compile(r"""os\.environ\.get\s*\(\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),
    re.compile(r"""os\.getenv\s*\(\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),
    re.compile(r"""process\.env\.([A-Z_][A-Z0-9_]*)"""),
    re.compile(r"""\$\{([A-Z_][A-Z0-9_]*)\}"""),
    re.compile(r"""ENV\[['"]([A-Z_][A-Z0-9_]*)['"]"""),  # Ruby
    re.compile(r"""getenv\s*\(\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),  # PHP/C
    re.compile(r"""System\.getenv\s*\(\s*"([A-Z_][A-Z0-9_]*)"""),  # Java
    re.compile(r"""std::env::var\s*\(\s*"([A-Z_][A-Z0-9_]*)"""),  # Rust
]

# Pattern for Docker Compose environment variable references: ${VAR} or $VAR
DOCKER_VAR_RE = re.compile(
    r"\$\{([A-Z_][A-Z0-9_]*?)(?::-[^}]*)?\}|\$([A-Z_][A-Z0-9_]*)"
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AuditResult:
    """Result of an .env audit.

    Attributes:
        undocumented: In .env but not in .env.example.
        missing_locally: In .env.example but not in .env.
        unused: Declared but never referenced in source or docker files.
        unknown: Referenced in source but not declared anywhere.
        docker_declared: Variables declared in Docker Compose files.
    """

    undocumented: List[str] = field(default_factory=list)
    missing_locally: List[str] = field(default_factory=list)
    unused: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    docker_declared: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_env_file(path: str) -> Dict[str, str]:
    """Parse a .env style file and return variable names mapped to masked values.

    Secret values are replaced with '<REDACTED>' so they never appear in output.

    Args:
        path: Path to the .env file.

    Returns:
        Dict mapping variable name → '<REDACTED>'.

    Raises:
        SystemExit: If the file cannot be read.
    """
    result: Dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                # Handle export VAR=value syntax
                line = re.sub(r"^export\s+", "", line)
                if "=" in line:
                    key = line.split("=", 1)[0].strip()
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                        result[key] = "<REDACTED>"
    except OSError as exc:
        logger.error("Cannot read env file '%s': %s", path, exc)
        sys.exit(1)
    return result


def parse_docker_compose_env_vars(paths: List[str]) -> Set[str]:
    """Extract environment variable names referenced in Docker Compose files.

    Args:
        paths: List of Docker Compose file paths.

    Returns:
        Set of variable names found.
    """
    vars_found: Set[str] = set()
    for path in paths:
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            logger.warning("Cannot read docker file '%s'", path)
            continue

        for match in DOCKER_VAR_RE.finditer(content):
            var = match.group(1) or match.group(2)
            if var:
                vars_found.add(var)
        # Also parse 'environment:' block keys
        # Matches lines like:  - MY_VAR=value  or  MY_VAR: value
        for line in content.splitlines():
            stripped = line.strip().lstrip("-").strip()
            if "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if re.match(r"^[A-Z_][A-Z0-9_]*$", key):
                    vars_found.add(key)
            elif ":" in stripped:
                key = stripped.split(":", 1)[0].strip()
                if re.match(r"^[A-Z_][A-Z0-9_]*$", key):
                    vars_found.add(key)
    return vars_found


def find_docker_compose_files(root: str) -> List[str]:
    """Find Docker Compose files in a directory.

    Args:
        root: Root directory to search.

    Returns:
        List of absolute paths to found Compose files.
    """
    found: List[str] = []
    for entry in os.scandir(root):
        if entry.is_file():
            for pattern in DOCKER_COMPOSE_PATTERNS:
                if fnmatch.fnmatch(entry.name.lower(), pattern.lower()):
                    found.append(entry.path)
                    break
    return found


def scan_source_for_usage(
    root: str,
    extensions: Tuple[str, ...],
    exclude_dirs: Tuple[str, ...],
) -> Set[str]:
    """Recursively scan source files for environment variable references.

    Args:
        root: Root directory to scan.
        extensions: File extensions to include.
        exclude_dirs: Directory names to skip.

    Returns:
        Set of variable names referenced in source.
    """
    referenced: Set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs in-place
        dirnames[:] = [
            d for d in dirnames if d not in exclude_dirs and not d.startswith(".")
        ]
        for filename in filenames:
            if not any(filename.endswith(ext) for ext in extensions):
                continue
            fpath = os.path.join(dirpath, filename)
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pattern in VAR_USAGE_PATTERNS:
                for match in pattern.finditer(content):
                    referenced.add(match.group(1))

    return referenced


# ---------------------------------------------------------------------------
# Core audit
# ---------------------------------------------------------------------------


# pylint: disable=too-many-arguments,too-many-positional-arguments
def audit(
    env_path: str,
    example_path: Optional[str],
    source_root: str,
    source_extensions: Tuple[str, ...],
    exclude_dirs: Tuple[str, ...],
    docker_files: List[str],
) -> AuditResult:
    """Run the full .env audit.

    Args:
        env_path: Path to the .env file.
        example_path: Path to the .env.example file (optional).
        source_root: Root directory for source code scanning.
        source_extensions: File extensions to scan.
        exclude_dirs: Directories to exclude from scan.
        docker_files: Paths to Docker Compose files.

    Returns:
        AuditResult with all findings.
    """
    result = AuditResult()

    # Parse files
    env_vars: Set[str] = set(parse_env_file(env_path).keys())
    example_vars: Set[str] = set()
    if example_path and os.path.isfile(example_path):
        example_vars = set(parse_env_file(example_path).keys())

    # Docker vars
    docker_vars: Set[str] = set()
    if docker_files:
        docker_vars = parse_docker_compose_env_vars(docker_files)
        result.docker_declared = sorted(docker_vars)

    # Source code usage
    logger.info("Scanning source code in '%s'…", source_root)
    used_in_source = scan_source_for_usage(source_root, source_extensions, exclude_dirs)

    all_declared = env_vars | example_vars | docker_vars
    all_consumed = used_in_source | docker_vars

    # 1. Undocumented: in .env but not in .env.example
    if example_path:
        result.undocumented = sorted(env_vars - example_vars)

    # 2. Missing locally: in .env.example but not in .env
    if example_path:
        result.missing_locally = sorted(example_vars - env_vars)

    # 3. Unused: declared in .env (or .env.example) but never used in source or docker
    result.unused = sorted(all_declared - all_consumed)

    # 4. Unknown: used in source but not declared anywhere
    result.unknown = sorted(used_in_source - all_declared)

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(
    result: AuditResult, env_path: str, example_path: Optional[str]
) -> None:
    """Print a formatted audit report.

    Args:
        result: AuditResult to display.
        env_path: Path to the .env file.
        example_path: Path to .env.example, or None.
    """
    print(f"\n{'=' * 60}")
    print("  .env Audit Report")
    print(f"  .env          : {env_path}")
    print(f"  .env.example  : {example_path or 'N/A'}")
    print(f"{'=' * 60}\n")

    def _section(title: str, items: List[str], color_ok: str = "✅") -> None:
        print(f"── {title} ──")
        if items:
            for v in items:
                print(f"  ⚠  {v}")
        else:
            print(f"  {color_ok} None")
        print()

    _section("Undocumented (in .env, missing from .env.example)", result.undocumented)
    _section(
        "Missing Locally (in .env.example, missing from .env)", result.missing_locally
    )
    _section("Unused Variables (declared but never referenced in code)", result.unused)
    _section("Unknown Variables (used in code but not declared)", result.unknown)

    if result.docker_declared:
        print("── Docker Compose Declared Variables ────────────────────")
        for v in result.docker_declared:
            print(f"  {v}")
        print()

    print("=" * 60)
    total_issues = (
        len(result.undocumented)
        + len(result.missing_locally)
        + len(result.unused)
        + len(result.unknown)
    )
    print(f"  Total issues: {total_issues}")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            ".env Auditor — compare .env, .env.example, "
            "Docker files, and source code."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python env_auditor.py
  python env_auditor.py --env .env.production --example .env.example --source ./src
  python env_auditor.py --docker docker-compose.yml --exclude node_modules dist
""",
    )
    parser.add_argument(
        "--env",
        default=".env",
        metavar="FILE",
        help="Path to the .env file (default: .env).",
    )
    parser.add_argument(
        "--example",
        default=".env.example",
        metavar="FILE",
        help="Path to the .env.example file (default: .env.example).",
    )
    parser.add_argument(
        "--source",
        default=".",
        metavar="DIR",
        help="Root directory to scan for source code (default: current directory).",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=list(DEFAULT_SOURCE_EXTS),
        metavar="EXT",
        help="File extensions to scan (default: common code extensions).",
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        default=["node_modules", ".venv", "venv", "dist", "build", ".git"],
        metavar="DIR",
        help="Directory names to exclude from source scan.",
    )
    parser.add_argument(
        "--docker",
        nargs="+",
        default=None,
        metavar="FILE",
        help="Docker Compose files to check (auto-detected if not specified).",
    )
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Exit with code 1 if any issues are found.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    env_path = os.path.abspath(args.env)
    if not os.path.isfile(env_path):
        logger.error("'.env' file not found: %s", env_path)
        sys.exit(1)

    example_path: Optional[str] = None
    if args.example:
        candidate = os.path.abspath(args.example)
        if os.path.isfile(candidate):
            example_path = candidate
        else:
            logger.warning(
                ".env.example not found at '%s' — skipping comparison.", candidate
            )

    source_root = os.path.abspath(args.source)
    if not os.path.isdir(source_root):
        logger.error("Source directory not found: %s", source_root)
        sys.exit(1)

    # Resolve Docker files
    docker_files: List[str] = []
    if args.docker:
        docker_files = [os.path.abspath(p) for p in args.docker if os.path.isfile(p)]
    else:
        docker_files = find_docker_compose_files(source_root)

    result = audit(
        env_path=env_path,
        example_path=example_path,
        source_root=source_root,
        source_extensions=tuple(args.extensions),
        exclude_dirs=tuple(args.exclude),
        docker_files=docker_files,
    )

    print_report(result, env_path, example_path)

    if args.fail_on_issues:
        total = (
            len(result.undocumented)
            + len(result.missing_locally)
            + len(result.unused)
            + len(result.unknown)
        )
        if total > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()

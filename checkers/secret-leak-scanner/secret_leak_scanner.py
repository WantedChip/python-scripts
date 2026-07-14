#!/usr/bin/env python3
"""Secret Leak Scanner for Personal Repos.

Detects API key patterns, private keys, database credentials, and generic secrets
using regular expressions and Shannon entropy analysis, and provides safe
remediation guidance.
"""

import argparse
import math
import os
import re
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any, Generator, Pattern

# Common API key and credentials regex signatures
SIGNATURES: dict[str, Pattern[str]] = {
    "AWS Access Key ID": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "AWS Secret Access Key": re.compile(
        r"\b[A-Za-z0-9+/]{40}\b"
    ),  # Will be filtered by keyword/entropy check
    "Google Cloud/Firebase API Key": re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"),
    "GitHub Personal Access Token (Classic)": re.compile(r"\bghp_[a-zA-Z0-9]{36}\b"),
    "GitHub Personal Access Token (Fine-grained)": re.compile(
        r"\bgithub_pat_[a-zA-Z0-9]{82}\b"
    ),
    "Slack Bot Token": re.compile(r"\bxoxb-[0-9]{11,13}-[a-zA-Z0-9]{24}\b"),
    "Slack User Token": re.compile(r"\bxoxp-[0-9]{11,13}-[a-zA-Z0-9]{24}\b"),
    "Slack Webhook URL": re.compile(
        r"https://hooks\.slack\.com/services/"
        r"T[a-zA-Z0-9_]{8}/B[a-zA-Z0-9_]{8,9}/[a-zA-Z0-9_]{24}"
    ),
    "Stripe API Key": re.compile(r"\b(?:sk|pk)_(?:live|test)_[0-9a-zA-Z]{24,99}\b"),
    "Private SSH Key": re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY"),
    "Generic Credentials/API URL": re.compile(
        r"\b[a-zA-Z0-9+._-]+:[a-zA-Z0-9+._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
    ),
}

# Generic key-value secret pattern
GENERIC_KEY_VALUE_PATTERN: Pattern[str] = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|passwd|token|"
    r"auth[_-]?token|credential|private[_-]?key|access[_-]?key|"
    r"api[_-]?secret)\b\s*[:=]\s*[\"']([a-zA-Z0-9_/=+.-]{16,120})[\"']"
)

# Common placeholder substrings to ignore
PLACEHOLDERS: set[str] = {
    "placeholder",
    "dummy",
    "your_",
    "my_",
    "test_",
    "mock_",
    "example",
    "replace_me",
    "secret_key",
    "api_key_here",
    "token_here",
    "password_here",
}


def calculate_entropy(text: str) -> float:
    """Calculate the Shannon entropy of a string.

    Args:
        text: The string to analyze.

    Returns:
        The Shannon entropy as a float value.
    """
    if not text:
        return 0.0
    entropy = 0.0
    text_len = len(text)
    counts: dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    for count in counts.values():
        prob = count / text_len
        entropy -= prob * math.log2(prob)
    return entropy


def is_placeholder(secret: str) -> bool:
    """Check if the detected secret contains common placeholders.

    Args:
        secret: The secret string to check.

    Returns:
        True if the secret is likely a placeholder, False otherwise.
    """
    lower_secret = secret.lower()
    return any(p in lower_secret for p in PLACEHOLDERS)


def mask_secret(secret: str) -> str:
    """Mask a secret showing only the first and last 3 characters.

    Args:
        secret: The secret to mask.

    Returns:
        The masked secret string.
    """
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:3]}...{secret[-3:]}"


def scan_text(
    text: str, file_path: str, entropy_threshold: float
) -> list[dict[str, Any]]:
    """Scan a block of text for potential secrets.

    Args:
        text: The text to scan.
        file_path: The file path the text originates from.
        entropy_threshold: The Shannon entropy threshold for generic secrets.

    Returns:
        A list of findings, each containing the secret type, file path, line number,
        matched text, and masked secret.
    """
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()

    for line_idx, line in enumerate(lines, start=1):
        # 1. Check known signatures
        for name, pattern in SIGNATURES.items():
            for match in pattern.finditer(line):
                matched_str = match.group(0)
                if is_placeholder(matched_str):
                    continue
                # For AWS secrets, calculate entropy to avoid false positives
                if name == "AWS Secret Access Key":
                    if (
                        calculate_entropy(matched_str) < 3.5
                        or matched_str.isalnum()
                        and matched_str.islower()
                    ):
                        continue

                findings.append(
                    {
                        "type": name,
                        "file": file_path,
                        "line": line_idx,
                        "matched": matched_str,
                        "masked": mask_secret(matched_str),
                    }
                )

        # 2. Check generic key-value matches
        for match in GENERIC_KEY_VALUE_PATTERN.finditer(line):
            matched_secret = match.group(2)
            if is_placeholder(matched_secret):
                continue
            entropy = calculate_entropy(matched_secret)
            if entropy >= entropy_threshold:
                # Basic check to avoid normal file paths or identifiers
                if "/" in matched_secret and not matched_secret.startswith(
                    ("http", "mongodb", "postgres")
                ):
                    continue
                findings.append(
                    {
                        "type": f"High-Entropy Secret ({match.group(1)})",
                        "file": file_path,
                        "line": line_idx,
                        "matched": matched_secret,
                        "masked": mask_secret(matched_secret),
                    }
                )

    return findings


def get_git_staged_files() -> list[str]:
    """Get the list of files staged in the current Git repository.

    Returns:
        A list of staged file paths.
    """
    try:
        # Run git command safely with shell=False
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603 B607
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def get_git_staged_diff(file_path: str) -> str:
    """Get the staged diff of a file.

    Args:
        file_path: The file path.

    Returns:
        The staged diff lines.
    """
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--", file_path],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603 B607
        # Extract only lines starting with '+' and skip header lines
        added_lines: list[str] = []
        for line in res.stdout.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])
        return "\n".join(added_lines)
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def find_files_recursively(
    root_path: Path, exclude_patterns: list[str]
) -> Generator[Path, None, None]:
    """Find all files recursively, excluding configured paths.

    Args:
        root_path: The starting directory Path.
        exclude_patterns: Substrings or regexes to skip.

    Yields:
        Paths to matching files.
    """
    for root, dirs, files in os.walk(root_path):
        # Exclude directories in-place to prune walk
        for d in list(dirs):
            d_path = Path(root) / d
            d_posix = d_path.as_posix()
            if any(p in d_posix or re.search(p, d_posix) for p in exclude_patterns):
                dirs.remove(d)

        for f in files:
            f_path = Path(root) / f
            f_posix = f_path.as_posix()
            if any(p in f_posix or re.search(p, f_posix) for p in exclude_patterns):
                continue
            yield f_path


def print_remediation_guidance(findings: list[dict[str, Any]]) -> None:
    """Print safe remediation guidance to the user.

    Args:
        findings: The list of detected leak findings.
    """
    print("\n" + "=" * 60)
    print("🚨 SECRET SCANNER DETECTED LEAKS")
    print("=" * 60)
    for f in findings:
        print(
            f"📍 {f['file']}:{f['line']} -> [{f['type']}] | Masked Value: {f['masked']}"
        )

    print("\n" + "=" * 60)
    print("🛡️  SAFE REMEDIATION GUIDANCE")
    print("=" * 60)
    print("1. UNSTAGE THE COMPROMISED FILES:")
    print("   To remove a file from git staging area, run:")
    print("   git restore --staged <file_path>")
    print("\n2. MIGRATE CREDENTIALS TO ENV VARIABLES:")
    print("   Move the secret value into a local file named '.env' at project root:")
    print("   API_KEY=your_actual_secret_value_here")
    print("\n   Load them securely using python-dotenv in your code:")
    print("     import os")
    print("     from dotenv import load_dotenv")
    print("     load_dotenv()")
    print("     api_key = os.getenv('API_KEY')")
    print("\n3. IGNORE SENSITIVE FILES IN GIT:")
    print(
        "   Add '.env' and other key files to your project's "
        "'.gitignore' to prevent leaks:"
    )
    print("   echo '.env' >> .gitignore")
    print("\n4. IF SECRETS ARE ALREADY COMMITTED OR PUSHED:")
    print("   ⚠️  WARNING: Simply modifying the file and committing again does NOT")
    print(
        "   remove the credential from git history. It remains accessible "
        "in older commits."
    )
    print("   - Revoke/rotate the leaked key immediately.")
    print("   - Purge it from git history using git-filter-repo:")
    print("     git filter-repo --path <file_path> --invert-paths")
    print("   - Or use the BFG Repo-Cleaner:")
    print("     bfg --replace-text passwords.txt")
    print("=" * 60)


def scan_git_staged(entropy_threshold: float) -> list[dict[str, Any]]:
    """Scan git staged changes.

    Args:
        entropy_threshold: Shannon entropy threshold.

    Returns:
        List of findings.
    """
    findings: list[dict[str, Any]] = []
    staged_files = get_git_staged_files()
    if not staged_files:
        print("No staged files detected in Git.")
        sys.exit(0)

    binary_extensions = (
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".pdf",
        ".zip",
        ".exe",
        ".dll",
        ".so",
        ".bin",
    )

    for file_path in staged_files:
        if not os.path.exists(file_path):
            continue
        if file_path.endswith(binary_extensions):
            continue
        diff_text = get_git_staged_diff(file_path)
        if diff_text:
            file_findings = scan_text(diff_text, file_path, entropy_threshold)
            findings.extend(file_findings)
    return findings


def scan_local_paths(
    paths: list[str], exclude: list[str], entropy_threshold: float
) -> list[dict[str, Any]]:
    """Scan explicit files or directories.

    Args:
        paths: List of file/folder paths.
        exclude: Exclude patterns.
        entropy_threshold: Shannon entropy threshold.

    Returns:
        List of findings.
    """
    findings: list[dict[str, Any]] = []
    scan_paths = paths if paths else ["."]
    for p in scan_paths:
        path = Path(p)
        if not path.exists():
            print(f"Path does not exist: {p}")
            continue

        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                findings.extend(scan_text(text, str(path), entropy_threshold))
            except OSError as err:
                print(f"Error reading file {path}: {err}")
        elif path.is_dir():
            for f_path in find_files_recursively(path, exclude):
                try:
                    text = f_path.read_text(encoding="utf-8", errors="ignore")
                    findings.extend(scan_text(text, str(f_path), entropy_threshold))
                except OSError as err:
                    print(f"Error reading file {f_path}: {err}")
    return findings


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Secret Leak Scanner for Personal Repos."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "Files or directories to scan. "
            "Defaults to current directory if not git-staged."
        ),
    )
    parser.add_argument(
        "-g",
        "--git-staged",
        action="store_true",
        help="Scan git staged changes (only added lines in modified files).",
    )
    parser.add_argument(
        "-p",
        "--pre-commit",
        action="store_true",
        help=(
            "Pre-commit integration mode. "
            "Fails with non-zero exit code if secrets are detected."
        ),
    )
    parser.add_argument(
        "-e",
        "--entropy-threshold",
        type=float,
        default=4.5,
        help="Shannon entropy threshold for generic secrets (default: 4.5).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[
            r"\.git/",
            r"\.venv/",
            r"node_modules/",
            r"\.next/",
            r"__pycache__/",
            r"\.mypy_cache/",
            r"\.pytest_cache/",
        ],
        help=(
            "Substrings or regex patterns of paths to exclude "
            "from recursive directory scans."
        ),
    )

    args = parser.parse_args()

    if args.git_staged or args.pre_commit:
        findings = scan_git_staged(args.entropy_threshold)
    else:
        findings = scan_local_paths(args.paths, args.exclude, args.entropy_threshold)

    if findings:
        print_remediation_guidance(findings)
        if args.pre_commit or args.git_staged:
            sys.exit(1)
        sys.exit(0)
    else:
        print("✅ No secrets or credential leaks detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()

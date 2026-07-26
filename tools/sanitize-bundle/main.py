#!/usr/bin/env python3
"""Bundle Sanitizer Tool.

Recursively copies a project or log directory while redacting secrets,
IP addresses, emails, local user paths, and sensitive tokens with
deterministic placeholders to produce a shareable bundle.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=unused-argument

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

JWT_PATTERN = r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
SECRET_PATTERN = (
    r"(?i)(api[_-]?key|secret|token|password|auth)\s*[:=]\s*["
    r"'\"]?([A-Za-z0-9_\-.~+/=]{8,})['\"]?"
)  # nosec B105


class BundleSanitizer:
    """Sanitizes text files in a directory tree while preserving structure."""

    # Regex patterns for sensitive data detection
    EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    IPV4_REGEX = re.compile(
        r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
        r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
    )
    # AWS Access Key / Secret, Generic JWT, Bearer tokens, API Keys
    SECRET_REGEXES = [
        (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[AWS_KEY_ID]"),
        (re.compile(SECRET_PATTERN), "[REDACTED_SECRET]"),
        (
            re.compile(r"\bBearer\s+([A-Za-z0-9_\-\.=]+)\b"),
            "Bearer [REDACTED_TOKEN]",
        ),
        (re.compile(JWT_PATTERN), "[REDACTED_JWT]"),
    ]
    # Local Windows and Unix user paths
    PATH_REGEX = re.compile(
        r"(?:[a-zA-Z]:\\(?:Users|home)\\[^\s\\/:]+|(?:/home/|/Users/)[^\s\\/:]+)"
    )

    def __init__(self, custom_replacements: Optional[Dict[str, str]] = None):
        """Initialize the sanitizer.

        Args:
            custom_replacements: Optional mapping of strings to placeholders.
        """
        self.email_map: Dict[str, str] = {}
        self.ip_map: Dict[str, str] = {}
        self.path_map: Dict[str, str] = {}
        self.custom_map: Dict[str, str] = custom_replacements or {}

    def _get_deterministic_placeholder(
        self, value: str, category: str, mapping: Dict[str, str]
    ) -> str:
        """Return consistent placeholder for repeated sensitive values."""
        if value not in mapping:
            index = len(mapping) + 1
            mapping[value] = f"[{category}_{index}]"
        return mapping[value]

    def sanitize_text(self, text: str) -> str:
        """Sanitize input text by replacing sensitive information.

        Args:
            text: Raw input string.

        Returns:
            Sanitized string.
        """
        # 1. Custom explicit replacements
        for target, replacement in self.custom_map.items():
            text = text.replace(target, replacement)

        # 2. Email addresses
        def email_replacer(match: re.Match[str]) -> str:
            email = match.group(0)
            return str(
                self._get_deterministic_placeholder(email, "EMAIL", self.email_map)
            )

        text = self.EMAIL_REGEX.sub(email_replacer, text)

        # 3. IPv4 addresses (exclude loopback & broadcast)
        def ip_replacer(match: re.Match[str]) -> str:
            ip = match.group(0)
            if ip in ("127.0.0.1", "0.0.0.0", "255.255.255.255"):  # nosec B104
                return ip
            return str(self._get_deterministic_placeholder(ip, "IP", self.ip_map))

        text = self.IPV4_REGEX.sub(ip_replacer, text)

        # 4. User paths
        def path_replacer(match: re.Match[str]) -> str:
            path_str = match.group(0)
            return str(
                self._get_deterministic_placeholder(path_str, "PATH", self.path_map)
            )

        text = self.PATH_REGEX.sub(path_replacer, text)

        # 5. Secrets and Tokens
        for regex, tag in self.SECRET_REGEXES:
            if tag == "[REDACTED_SECRET]":

                def secret_sub(match: re.Match[str]) -> str:
                    val_part = match.group(2)
                    return str(match.group(0).replace(val_part, "[REDACTED_SECRET]"))

                text = regex.sub(secret_sub, text)
            else:
                text = regex.sub(tag, text)

        return text

    def is_binary(self, file_path: Path) -> bool:
        """Determine if a file is binary by scanning initial bytes."""
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                return b"\x00" in chunk
        except OSError:
            return True

    def sanitize_directory(
        self,
        src_dir: Path,
        dst_dir: Path,
        ignore_patterns: Optional[List[str]] = None,
    ) -> Tuple[int, int]:
        """Recursively copy and sanitize directory.

        Args:
            src_dir: Source directory path.
            dst_dir: Destination directory path.
            ignore_patterns: Glob patterns to ignore.

        Returns:
            Tuple of (text_files_sanitized, total_files_processed)
        """
        src_dir = src_dir.resolve()
        dst_dir = dst_dir.resolve()

        if not src_dir.is_dir():
            err_msg = (
                "Source directory does not exist or is not a directory:" f" {src_dir}"
            )
            raise ValueError(err_msg)

        sanitized_count = 0
        total_count = 0

        for root, _, files in os.walk(src_dir):
            rel_root = Path(root).relative_to(src_dir)
            target_root = dst_dir / rel_root
            target_root.mkdir(parents=True, exist_ok=True)

            for file_name in files:
                total_count += 1
                src_file = Path(root) / file_name
                dst_file = target_root / file_name

                if self.is_binary(src_file):
                    shutil.copy2(src_file, dst_file)
                else:
                    try:
                        with open(
                            src_file, "r", encoding="utf-8", errors="replace"
                        ) as f:
                            content = f.read()

                        sanitized_content = self.sanitize_text(content)

                        with open(dst_file, "w", encoding="utf-8") as f:
                            f.write(sanitized_content)

                        sanitized_count += 1
                    except OSError:
                        # Fallback copy if reading text fails
                        shutil.copy2(src_file, dst_file)

        return sanitized_count, total_count


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Sanitize project/log bundle before sharing."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-s", "--src", required=True, type=Path, help="Source directory"
    )
    parser.add_argument(
        "-d",
        "--dst",
        required=True,
        type=Path,
        help="Destination output directory",
    )
    parser.add_argument("--user", help="Explicit username to redact")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Bundle Sanitizer."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    custom_map = {}
    if parsed.user:
        custom_map[parsed.user] = "[USER_REDACTED]"

    sanitizer = BundleSanitizer(custom_replacements=custom_map)
    print(f"Sanitizing bundle from '{parsed.src}' to '{parsed.dst}'...")
    text_count, total_count = sanitizer.sanitize_directory(parsed.src, parsed.dst)
    print(
        f"Completed: Processed {total_count} files ({text_count} text files"
        " sanitized)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

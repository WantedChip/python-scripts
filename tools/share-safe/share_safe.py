#!/usr/bin/env python3
"""Share Safe.

Copies folders or files to a sanitized destination directory for bug reports,
automatically replacing usernames, home paths, IP addresses, tokens, and custom
identifiers.
"""

import argparse
import getpass
import os
import re
import shutil
import sys
from typing import List, Pattern, Tuple


def is_binary(file_path: str) -> bool:
    """Check if file is binary by looking for null bytes in initial chunk."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except OSError:
        return True


def redact_text(
    content: str, redactions: List[Tuple[Pattern[str], str]]
) -> Tuple[str, int]:
    """Apply compiled regex patterns to substitute sensitive content."""
    modified_content = content
    total_matches = 0
    for pattern, replacement in redactions:
        modified_content, count = pattern.subn(replacement, modified_content)
        total_matches += count
    return modified_content, total_matches


def compile_redactors(custom_keywords: List[str]) -> List[Tuple[Pattern[str], str]]:
    """Compile regular expressions for standard and user-defined redactors."""
    redactions: List[Tuple[Pattern[str], str]] = []

    # 1. Redact Username
    username = getpass.getuser()
    if username:
        redactions.append(
            (
                re.compile(r"\b" + re.escape(username) + r"\b", re.IGNORECASE),
                "[USER_REDACTED]",
            )
        )

    # 2. Redact Home Directory
    home = os.path.expanduser("~")
    if home:
        redactions.append(
            (re.compile(re.escape(home), re.IGNORECASE), "[HOME_REDACTED]")
        )
        win_home = home.replace("\\", "/")
        if win_home != home:
            redactions.append(
                (re.compile(re.escape(win_home), re.IGNORECASE), "[HOME_REDACTED]")
            )

    # 3. Redact IPv4 Addresses
    ipv4_pat = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")
    redactions.append((ipv4_pat, "[IP_REDACTED]"))

    # 4. Redact IPv6 Addresses
    ipv6_pat = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b")
    redactions.append((ipv6_pat, "[IPv6_REDACTED]"))

    # 5. Redact HTTP Authorizations / Token values
    token_pat = re.compile(
        r"(?i)(authorization:\s*)(?:bearer|basic)\s+[a-zA-Z0-9._~+/-]+=*"
    )
    redactions.append((token_pat, r"\1[TOKEN_REDACTED]"))

    # 6. Redact Custom API key formats
    key_pat = re.compile(
        r"(?i)(key|secret|password|token|passwd|credential)\s*[:=]\s*"
        r"['\"][a-zA-Z0-9._~+/-]{8,}['\"]"
    )
    redactions.append((key_pat, r"\1: '[REDACTED]'"))

    # 7. Redact Custom User-supplied keywords
    for kw in custom_keywords:
        if kw:
            redactions.append(
                (
                    re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE),
                    f"[REDACTED_{kw.upper()}]",
                )
            )

    return redactions


# pylint: disable=too-many-locals,too-many-branches
# pylint: disable=too-many-statements,too-many-nested-blocks
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Create sanitized copies of logs and directories by redacting "
            "sensitive data."
        )
    )
    parser.add_argument("source", help="Source file or directory to copy and sanitize.")
    parser.add_argument(
        "destination", help="Destination path where sanitized copy will be written."
    )
    parser.add_argument(
        "-c",
        "--custom-redact",
        help="Comma-separated list of custom words/identifiers to redact.",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help=(
            "Perform a dry run to output how many items match, without "
            "copying or writing files."
        ),
    )

    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f"Error: Source does not exist: {args.source}", file=sys.stderr)
        sys.exit(1)

    custom_keywords = (
        [k.strip() for k in args.custom_redact.split(",") if k.strip()]
        if args.custom_redact
        else []
    )
    redactors = compile_redactors(custom_keywords)

    source_abs = os.path.abspath(args.source)
    dest_abs = os.path.abspath(args.destination)

    if not args.dry_run and os.path.exists(dest_abs):
        print(f"Error: Destination already exists: {dest_abs}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("SHARE SAFE: RECOVERY AND REDACTION UTILITY")
    print("========================================================================")
    if args.dry_run:
        print("[!] Running in DRY-RUN mode. No files will be modified or copied.")

    files_processed = 0
    total_redactions = 0

    if os.path.isfile(source_abs):
        files_processed += 1
        is_bin = is_binary(source_abs)

        if is_bin:
            print(f"File: {os.path.basename(source_abs)} (Binary, copying directly)")
            if not args.dry_run:
                parent = os.path.dirname(dest_abs)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                shutil.copy2(source_abs, dest_abs)
        else:
            try:
                with open(source_abs, "r", encoding="utf-8", errors="replace") as sf:
                    content = sf.read()

                sanitized, matches = redact_text(content, redactors)
                total_redactions += matches
                b_name = os.path.basename(source_abs)
                msg = f"File: {b_name} (Text, flagged {matches} redaction matches)"
                print(msg)

                if not args.dry_run:
                    parent = os.path.dirname(dest_abs)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    with open(dest_abs, "w", encoding="utf-8") as df:
                        df.write(sanitized)
            except OSError as e:
                print(f"Error reading file {source_abs}: {e}", file=sys.stderr)
    else:
        for root, dirs, files in os.walk(source_abs):
            for d in dirs:
                src_dir = os.path.join(root, d)
                rel_dir = os.path.relpath(src_dir, source_abs)
                target_dir = os.path.join(dest_abs, rel_dir)
                if not args.dry_run:
                    os.makedirs(target_dir, exist_ok=True)

            for file_name in files:
                src_file = os.path.join(root, file_name)
                rel_file = os.path.relpath(src_file, source_abs)
                target_file = os.path.join(dest_abs, rel_file)

                files_processed += 1
                is_bin = is_binary(src_file)

                if not args.dry_run:
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)

                if is_bin:
                    if not args.dry_run:
                        shutil.copy2(src_file, target_file)
                else:
                    try:
                        with open(
                            src_file, "r", encoding="utf-8", errors="replace"
                        ) as fh:
                            content = fh.read()

                        sanitized, matches = redact_text(content, redactors)
                        total_redactions += matches
                        if matches > 0:
                            msg = (
                                f"Sanitizing: {rel_file} -> "
                                f"{matches} redactions applied"
                            )
                            print(msg)

                        if not args.dry_run:
                            with open(target_file, "w", encoding="utf-8") as fh:
                                fh.write(sanitized)
                    except OSError as e:
                        print(f"Error processing {src_file}: {e}", file=sys.stderr)

    print("\n" + "=" * 80)
    print("Sanitization Summary:")
    print(f"  Files processed: {files_processed:,}")
    print(f"  Total sensitive redactions applied: {total_redactions:,}")
    if not args.dry_run:
        print(f"  Sanitized copy successfully created at: {dest_abs}")
    print("=" * 80)


if __name__ == "__main__":
    main()

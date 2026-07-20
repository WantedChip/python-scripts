#!/usr/bin/env python3
"""Privacy Report.

Scans directories for potential privacy leaks (EXIF GPS, usernames in paths,
email addresses, API keys, hidden files, and document metadata) before sharing.
"""

import argparse
import getpass
import math
import os
import re
import stat
import sys
from typing import List, Tuple

# Optional PIL and pypdf imports
try:
    from PIL import Image
    from PIL.ExifTags import GPSTAGS, TAGS

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pypdf

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


def calculate_entropy(text: str) -> float:
    """Calculate Shannon entropy of a string to detect potential keys."""
    if not text:
        return 0.0
    entropy = 0.0
    length = len(text)
    frequencies: dict[str, int] = {}
    for char in text:
        frequencies[char] = frequencies.get(char, 0) + 1
    for count in frequencies.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def check_exif_gps(file_path: str) -> Tuple[bool, str]:
    """Check if image contains GPS EXIF coordinates."""
    if not HAS_PIL:
        return False, "PIL library not installed"
    try:
        with Image.open(file_path) as img:
            get_exif_fn = getattr(img, "_getexif", None)
            exif = get_exif_fn() if callable(get_exif_fn) else None
            if not exif:
                return False, ""

            for tag_id, value in exif.items():
                tag_name = TAGS.get(tag_id, tag_id)
                if tag_name == "GPSInfo":
                    gps_data = {}
                    for g_id, g_val in value.items():
                        g_tag = GPSTAGS.get(g_id, g_id)
                        gps_data[g_tag] = g_val
                    return True, f"GPS metadata found: {list(gps_data.keys())}"
    except (OSError, ValueError, KeyError, AttributeError):
        return False, "EXIF read error"
    return False, ""


def check_pdf_metadata(file_path: str) -> Tuple[bool, str]:
    """Check if PDF contains author, creator, or software metadata."""
    if not HAS_PYPDF:
        return False, "pypdf library not installed"
    try:
        reader = pypdf.PdfReader(file_path)
        meta = reader.metadata
        if meta:
            leak_details = []
            if meta.author:
                leak_details.append(f"Author: {meta.author}")
            if meta.creator:
                leak_details.append(f"Creator: {meta.creator}")
            if meta.producer:
                leak_details.append(f"Producer/Software: {meta.producer}")
            if leak_details:
                return True, "Metadata fields found: " + ", ".join(leak_details)
    except (OSError, ValueError, AttributeError, KeyError):
        return False, "PDF read error"
    return False, ""


def is_hidden_file(file_path: str) -> bool:
    """Identify if file is hidden (starts with dot or has Windows hidden attribute)."""
    base_name = os.path.basename(file_path)
    if base_name.startswith("."):
        return True

    if sys.platform == "win32":
        try:
            attrs = os.stat(file_path).st_file_attributes
            if attrs & stat.FILE_ATTRIBUTE_HIDDEN:
                return True
        except OSError:
            pass
    return False


# pylint: disable=too-many-locals
def scan_text_file(file_path: str, username: str) -> List[Tuple[str, str, int]]:
    """Scan text file content for leaks (emails, usernames, high-entropy keys)."""
    findings: List[Tuple[str, str, int]] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return findings

    # 1. Email Leak
    email_regex = r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
    emails = re.findall(email_regex, content)
    for email in set(emails):
        findings.append(("Warning", f"Email address found: '{email}'", 0))

    # 2. Username Leak
    if username:
        # Match word boundaries for username to avoid substring overlaps
        user_regex = r"\b" + re.escape(username) + r"\b"
        matches = re.findall(user_regex, content, re.IGNORECASE)
        if matches:
            msg = (
                f"System username '{username}' found in text content "
                f"({len(matches)} times)"
            )
            findings.append(("Warning", msg, 0))

    # 3. API Keys/Secrets (Entropy + Keyword Heuristics)
    secret_keywords = [
        "aws_key",
        "secret",
        "private_key",
        "password",
        "token",
        "apikey",
    ]
    lines = content.split("\n")
    for line_num, line in enumerate(lines, 1):
        line_lower = line.lower()

        # Check keyword matches
        for kw in secret_keywords:
            if kw in line_lower:
                # Flag if it contains assignment-like patterns
                if re.search(r"=\s*['\"][a-zA-Z0-9._%-]{8,}['\"]", line):
                    msg = (
                        f"Potential secret/key match for keyword '{kw}' "
                        f"at line {line_num}"
                    )
                    findings.append(("Critical", msg, line_num))
                    break

        # Check Shannon entropy for long words/strings
        words = re.findall(r"\b[a-zA-Z0-9_-]{16,}\b", line)
        for word in words:
            entropy = calculate_entropy(word)
            if entropy > 4.5:
                msg = (
                    f"High entropy string detected at line {line_num} "
                    f"(entropy: {entropy:.2f})"
                )
                findings.append(("Critical", msg, line_num))
                break

    return findings


# pylint: disable=too-many-locals,too-many-branches
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Scan directory before sharing to flag potential privacy leaks."
    )
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=".",
        help="Folder to scan recursively (default: current directory).",
    )

    args = parser.parse_args()

    if not os.path.exists(args.target_dir):
        print(f"Error: Directory does not exist: {args.target_dir}", file=sys.stderr)
        sys.exit(1)

    username = getpass.getuser()

    print("========================================================================")
    print("PRIVACY REPORT SCANNER")
    print("========================================================================")
    print(f"Scanning target: {os.path.abspath(args.target_dir)}")
    print(f"Current System Username signature: '{username}'")
    print("-" * 80)

    # Walk directories
    reports = []

    for root, dirs, files in os.walk(args.target_dir):
        # Scan dirs for usernames or hidden attributes
        for d in dirs:
            d_path = os.path.abspath(os.path.join(root, d))
            if is_hidden_file(d_path):
                reports.append((d_path, "Info", "Hidden directory flagged", ""))
            if username.lower() in d.lower():
                reports.append(
                    (
                        d_path,
                        "Warning",
                        f"Username '{username}' leaked in directory name",
                        "",
                    )
                )

        for f in files:
            f_path = os.path.abspath(os.path.join(root, f))
            _, ext = os.path.splitext(f.lower())

            # Check hidden file
            if is_hidden_file(f_path):
                reports.append((f_path, "Info", "Hidden file flagged", ""))

            # Check filename leakage
            if username.lower() in f.lower():
                reports.append(
                    (f_path, "Warning", f"Username '{username}' leaked in filename", "")
                )

            # Image EXIF checks
            if ext in (".jpg", ".jpeg", ".png"):
                has_gps, details = check_exif_gps(f_path)
                if has_gps:
                    reports.append((f_path, "Critical", details, ""))

            # PDF metadata checks
            elif ext == ".pdf":
                has_meta, details = check_pdf_metadata(f_path)
                if has_meta:
                    reports.append((f_path, "Warning", details, ""))

            # Text content scans
            elif ext in (
                ".txt",
                ".md",
                ".json",
                ".yaml",
                ".yml",
                ".ini",
                ".conf",
                ".cfg",
                ".log",
                ".py",
                ".js",
                ".html",
            ):
                findings = scan_text_file(f_path, username)
                for level, detail, line in findings:
                    line_suffix = f" (line {line})" if line > 0 else ""
                    reports.append((f_path, level, detail + line_suffix, ""))

    if not reports:
        print("\n[+] No privacy leaks flagged. Folder is safe to share!")
        sys.exit(0)

    # Sort results by Severity (Critical, Warning, Info)
    severity_order = {"Critical": 1, "Warning": 2, "Info": 3}
    reports.sort(key=lambda x: severity_order.get(x[1], 4))

    print(f"\nFlagged {len(reports)} privacy issues:")
    print("=" * 80)

    for path, level, desc, _ in reports:
        lvl_marker = f"[{level}]"
        rel_path = os.path.relpath(path, os.path.abspath(args.target_dir))
        print(f"{lvl_marker:<10} File: {rel_path}")
        print(f"           Details: {desc}")
        print("-" * 80)


if __name__ == "__main__":
    main()

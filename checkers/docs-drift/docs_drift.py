#!/usr/bin/env python3
"""Docs Drift.

Audits Markdown documentation files, checks referenced file paths, configuration
keys, and API names, and reports references that no longer exist.
"""

import argparse
import os
import re
import sys
from typing import Any, Dict, List, Set


def gather_codebase_words(src_dir: str) -> Set[str]:
    """Scan all source code files to build a vocabulary of defined symbols."""
    words = set()
    exclude_dirs = {
        ".git",
        "venv",
        ".venv",
        "node_modules",
        "build",
        "dist",
        "__pycache__",
    }

    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith((".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml")):
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                        # Extract alpha-numeric words
                        for w in re.findall(r"\b[a-zA-Z0-9_]+\b", content):
                            words.add(w)
                except OSError:
                    pass
    return words


# pylint: disable=too-many-locals
def check_docs_drift(docs_dir: str, code_words: Set[str]) -> List[Dict[str, Any]]:
    """Scan documents and verify that referenced file paths and API keys exist."""
    drifts = []
    exclude_dirs = {".git", "venv", ".venv", "node_modules", "build", "dist"}

    # Pattern to find Markdown link destinations: [text](link)
    # Filter for local file paths (ignore web URLs starting with http)
    link_pattern = re.compile(r"\[[^\]]*\]\(([^:\)]+)\)")

    # Pattern for code-quotes config keys or APIs: `CONFIG_KEY` or `my_function`
    code_quote_pattern = re.compile(r"`([a-zA-Z0-9_\-\.\/]+)`")

    for root, dirs, files in os.walk(docs_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith((".md", ".txt")):
                fpath = os.path.abspath(os.path.join(root, f))
                rel_doc = os.path.relpath(fpath, docs_dir)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        for line_num, line in enumerate(fh, 1):

                            # 1. Check file links
                            for m in link_pattern.finditer(line):
                                link_dest = (
                                    m.group(1).split("#")[0].strip()
                                )  # Strip anchor
                                if (
                                    not link_dest
                                    or link_dest.startswith("http")
                                    or link_dest.startswith("mailto")
                                ):
                                    continue

                                # Resolve relative to the document's directory
                                target_abs = os.path.abspath(
                                    os.path.join(os.path.dirname(fpath), link_dest)
                                )
                                if not os.path.exists(target_abs):
                                    drifts.append(
                                        {
                                            "file": rel_doc,
                                            "line": line_num,
                                            "reference": link_dest,
                                            "type": "Broken Link / Path",
                                            "reason": (
                                                "Referenced file or folder path "
                                                "does not exist on disk."
                                            ),
                                        }
                                    )

                            # 2. Check code quote keywords (API symbols / env vars)
                            for m in code_quote_pattern.finditer(line):
                                val = m.group(1).strip()
                                # Ignore small words, numbers, or paths with dots
                                if (
                                    len(val) < 4
                                    or val.isdigit()
                                    or "/" in val
                                    or "\\" in val
                                ):
                                    continue

                                # If word does not exist anywhere in codebase files
                                if val not in code_words:
                                    drifts.append(
                                        {
                                            "file": rel_doc,
                                            "line": line_num,
                                            "reference": val,
                                            "type": "Stale Code Reference",
                                            "reason": (
                                                f"API symbol, function, or config key "
                                                f"'{val}' not found in codebase files."
                                            ),
                                        }
                                    )
                except OSError:
                    pass
    return drifts


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify references in documentation (file paths, configurations, "
            "API names) against codebase."
        )
    )
    parser.add_argument(
        "--docs",
        default=".",
        help=(
            "Documentation folder containing markdown files (default: current "
            "directory)."
        ),
    )
    parser.add_argument(
        "--src",
        default=".",
        help="Source directory containing codebase (default: current directory).",
    )

    args = parser.parse_args()

    docs_dir = os.path.abspath(args.docs)
    src_dir = os.path.abspath(args.src)

    print("========================================================================")
    print("DOCS DRIFT: DOCUMENTATION STALENESS AUDITOR")
    print("========================================================================")
    print(f"Docs folder: {docs_dir}")
    print(f"Code folder: {src_dir}")
    print("Indexing codebase API vocabulary...")

    code_words = gather_codebase_words(src_dir)
    print(f"Indexed {len(code_words):,} words from codebase.")
    print("Scanning documentation files for drifts...")
    print("-" * 80)

    drifts = check_docs_drift(docs_dir, code_words)

    if not drifts:
        print(
            "\n[+] Success: All file paths, configuration keys, and API references "
            "match the active codebase."
        )
        sys.exit(0)

    print(f"\n[!] Discovered {len(drifts)} drift issues in documentation:")
    print("=" * 80)
    for idx, d in enumerate(drifts, 1):
        print(f"{idx}. File: {d['file']} (Line: {d['line']})")
        print(f"   Reference: {d['reference']}")
        print(f"   Issue:     {d['type']} - {d['reason']}")
        print("-" * 80)


if __name__ == "__main__":
    main()

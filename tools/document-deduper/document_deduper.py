#!/usr/bin/env python3
"""Document Deduper.

Detects near-duplicate PDF, DOCX, and text documents using shingle-based
Jaccard similarity computations.
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET  # nosec B405
import zipfile
from typing import Dict, List, Set

# Optional pypdf import
try:
    import pypdf

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


def extract_text_txt(file_path: str) -> str:
    """Read plain text/markdown file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def extract_text_docx(file_path: str) -> str:
    """Extract text from Word .docx file using native zip and xml parser."""
    try:
        texts = []
        with zipfile.ZipFile(file_path) as docx:
            xml_content = docx.read("word/document.xml")
            root = ET.fromstring(xml_content)  # nosec B314
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            for elem in root.findall(".//w:t", ns):
                if elem.text:
                    texts.append(elem.text)
        return " ".join(texts)
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError):
        return ""


def extract_text_pdf(file_path: str) -> str:
    """Extract text from PDF using pypdf library."""
    if not HAS_PYPDF:
        return ""
    try:
        texts = []
        reader = pypdf.PdfReader(file_path)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                texts.append(extracted)
        return " ".join(texts)
    except (OSError, ValueError):
        return ""


def get_document_text(file_path: str) -> str:
    """Direct files to their corresponding extension loaders."""
    _, ext = os.path.splitext(file_path.lower())
    if ext in (".txt", ".md", ".markdown", ".csv", ".json", ".html"):
        return extract_text_txt(file_path)
    if ext == ".docx":
        return extract_text_docx(file_path)
    if ext == ".pdf":
        return extract_text_pdf(file_path)
    return ""


def tokenize(text: str) -> List[str]:
    """Clean and split text into lowercase word tokens."""
    text_clean = re.sub(r"[^\w\s]", " ", text.lower())
    return [word for word in text_clean.split() if word]


def get_shingles(tokens: List[str], n: int) -> Set[str]:
    """Create N-gram shingles from a list of tokens."""
    shingles = set()
    for i in range(len(tokens) - n + 1):
        shingle = " ".join(tokens[i : i + n])  # noqa: E203
        shingles.add(shingle)
    return shingles


def calculate_jaccard(set1: Set[str], set2: Set[str]) -> float:
    """Compute Jaccard Similarity between two sets."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union


# pylint: disable=too-many-locals,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Detect near-duplicate PDF, DOCX, and text files based on "
            "content similarity."
        )
    )
    parser.add_argument(
        "directory", help="Directory containing documents to scan recursively."
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=85.0,
        help="Similarity threshold percentage (0.0 to 100.0, default: 85.0).",
    )
    parser.add_argument(
        "-s",
        "--shingle-size",
        type=int,
        default=3,
        help="N-gram shingle word size (default: 3).",
    )

    args = parser.parse_args()

    if not os.path.exists(args.directory):
        print(f"Error: Directory does not exist: {args.directory}", file=sys.stderr)
        sys.exit(1)

    threshold_ratio = args.threshold / 100.0
    supported_extensions = (".pdf", ".docx", ".txt", ".md", ".markdown")

    print("========================================================================")
    print("DOCUMENT DEDUPER: NEAR-DUPLICATE SCAN")
    print("========================================================================")
    if not HAS_PYPDF:
        print(
            "Warning: pypdf package is not installed. PDF extraction will be skipped."
        )
        print("To support PDF files, run: pip install pypdf")
        print("-" * 80)

    doc_shingles: Dict[str, Set[str]] = {}
    doc_paths: List[str] = []

    print(f"Scanning files in {args.directory}...")
    for root, _, files in os.walk(args.directory):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in supported_extensions:
                continue

            full_path = os.path.abspath(os.path.join(root, f))
            text = get_document_text(full_path)
            if not text.strip():
                continue

            tokens = tokenize(text)
            if len(tokens) < args.shingle_size:
                continue

            shingles = get_shingles(tokens, args.shingle_size)
            doc_shingles[full_path] = shingles
            doc_paths.append(full_path)

    print(
        f"Loaded {len(doc_paths):,} text-valid documents. Running similarity checks..."
    )

    duplicates_found = 0

    for i, path1 in enumerate(doc_paths):
        shingles1 = doc_shingles[path1]

        for j in range(i + 1, len(doc_paths)):
            path2 = doc_paths[j]
            shingles2 = doc_shingles[path2]

            jaccard = calculate_jaccard(shingles1, shingles2)

            if jaccard >= threshold_ratio:
                duplicates_found += 1
                name1 = os.path.basename(path1)
                name2 = os.path.basename(path2)

                print(f"\n[!] MATCH FOUND: Similarity {jaccard * 100.0:.1f}%")
                print(f"  File A: {name1}")
                print(f"          {path1}")
                print(f"  File B: {name2}")
                print(f"          {path2}")

    print("\n" + "=" * 80)
    print(f"Scan Summary: Detected {duplicates_found} near-duplicate pairs.")
    print("=" * 80)


if __name__ == "__main__":
    main()

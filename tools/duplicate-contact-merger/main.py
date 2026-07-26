"""Duplicate Contact Merger CLI Tool.

Identifies and merges duplicate contact records from CSV files using fuzzy
name matching (difflib.SequenceMatcher) and exact match keys on email/phone.
Resolves field conflicts using configurable strategies (prefer non-null,
prefer longest).
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import csv
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def calculate_name_similarity(name1: str, name2: str) -> float:
    """Calculate fuzzy similarity ratio between two names.

    Args:
        name1: First name string.
        name2: Second name string.

    Returns:
        Similarity score between 0.0 and 1.0.
    """
    n1 = name1.strip().lower()
    n2 = name2.strip().lower()
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0
    return difflib.SequenceMatcher(None, n1, n2).ratio()


def normalize_email_key(email: str) -> str:
    """Normalize email for exact matching key.

    Args:
        email: Email string.

    Returns:
        Lowercased trimmed email string.
    """
    return email.strip().lower() if email else ""


def normalize_phone_key(phone: str) -> str:
    """Normalize phone for exact matching key by extracting digits.

    Args:
        phone: Phone string.

    Returns:
        Extracted digit string.
    """
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    return digits if len(digits) >= 7 else ""


def are_contacts_duplicate(
    rec1: Dict[str, str],
    rec2: Dict[str, str],
    name_col: Optional[str],
    email_col: Optional[str],
    phone_col: Optional[str],
    threshold: float = 0.85,
) -> bool:
    """Determine if two contact records are duplicates based on fields.

    Args:
        rec1: Dictionary representing first record.
        rec2: Dictionary representing second record.
        name_col: Column name for contact name.
        email_col: Column name for email address.
        phone_col: Column name for phone number.
        threshold: Fuzzy match ratio threshold for names.

    Returns:
        True if records are considered duplicates, False otherwise.
    """
    # 1. Exact email match check
    if email_col and email_col in rec1 and email_col in rec2:
        e1 = normalize_email_key(rec1[email_col])
        e2 = normalize_email_key(rec2[email_col])
        if e1 and e2 and e1 == e2:
            return True

    # 2. Exact normalized phone match check
    if phone_col and phone_col in rec1 and phone_col in rec2:
        p1 = normalize_phone_key(rec1[phone_col])
        p2 = normalize_phone_key(rec2[phone_col])
        if p1 and p2 and p1 == p2:
            return True

    # 3. Fuzzy name match check
    if name_col and name_col in rec1 and name_col in rec2:
        n1 = rec1[name_col]
        n2 = rec2[name_col]
        if n1 and n2:
            sim = calculate_name_similarity(n1, n2)
            if sim >= threshold:
                return True

    return False


def cluster_duplicate_contacts(
    records: List[Dict[str, str]],
    name_col: Optional[str],
    email_col: Optional[str],
    phone_col: Optional[str],
    threshold: float = 0.85,
) -> List[List[Dict[str, str]]]:
    """Group contact records into duplicate clusters using graph components.

    Args:
        records: List of record dictionaries.
        name_col: Column name for contact name.
        email_col: Column name for email address.
        phone_col: Column name for phone number.
        threshold: Similarity threshold.

    Returns:
        List of record clusters (each cluster is a list of record dicts).
    """
    n = len(records)
    parent = list(range(n))

    def find(i: int) -> int:
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i: int, j: int) -> None:
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    for i in range(n):
        for j in range(i + 1, n):
            if are_contacts_duplicate(
                records[i],
                records[j],
                name_col,
                email_col,
                phone_col,
                threshold,
            ):
                union(i, j)

    clusters_map: Dict[int, List[Dict[str, str]]] = {}
    for i in range(n):
        root = find(i)
        if root not in clusters_map:
            clusters_map[root] = []
        clusters_map[root].append(records[i])

    return list(clusters_map.values())


def merge_cluster(
    cluster: List[Dict[str, str]],
    headers: List[str],
    strategy: str = "prefer_longest",
) -> Dict[str, str]:
    """Merge a cluster of duplicate record dicts into a single golden record.

    Args:
        cluster: List of records in the cluster.
        headers: List of CSV headers.
        strategy: Merge strategy ('prefer_non_null' or 'prefer_longest').

    Returns:
        Merged record dictionary.
    """
    if len(cluster) == 1:
        return dict(cluster[0])

    merged: Dict[str, str] = {}
    for field in headers:
        values = [r.get(field, "").strip() for r in cluster if r.get(field, "").strip()]
        if not values:
            merged[field] = ""
        elif strategy == "prefer_longest":
            # Sort by length descending, pick longest
            values.sort(key=len, reverse=True)
            merged[field] = values[0]
        else:  # prefer_non_null / first non-empty
            merged[field] = values[0]

    return merged


def process_merge_csv(
    input_file: Path,
    output_file: Path,
    name_col: Optional[str] = None,
    email_col: Optional[str] = None,
    phone_col: Optional[str] = None,
    threshold: float = 0.85,
    strategy: str = "prefer_longest",
    log_file: Optional[Path] = None,
) -> Tuple[int, int]:
    """Process CSV file, detect duplicate clusters, merge, and export.

    Args:
        input_file: Input CSV path.
        output_file: Output CSV path.
        name_col: Name column header.
        email_col: Email column header.
        phone_col: Phone column header.
        threshold: Fuzzy similarity threshold.
        strategy: Merge resolution strategy.
        log_file: Optional JSON log file path.

    Returns:
        Tuple of (original_count, merged_count).
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file non-existent: {input_file}")

    with input_file.open("r", encoding="utf-8-sig", newline="") as infile:
        reader = csv.DictReader(infile)
        if not reader.fieldnames:
            raise ValueError("CSV file missing headers or empty.")
        fieldnames = list(reader.fieldnames)
        records = list(reader)

    original_count = len(records)
    if original_count == 0:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
        return 0, 0

    clusters = cluster_duplicate_contacts(
        records, name_col, email_col, phone_col, threshold=threshold
    )

    merged_records = [merge_cluster(c, fieldnames, strategy=strategy) for c in clusters]
    merged_count = len(merged_records)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_records)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        cluster_summary = [
            {"cluster_id": idx + 1, "record_count": len(c), "records": c}
            for idx, c in enumerate(clusters)
            if len(c) > 1
        ]
        log_data = {
            "original_count": original_count,
            "merged_count": merged_count,
            "duplicates_removed": original_count - merged_count,
            "clusters_merged": len(cluster_summary),
            "merged_clusters": cluster_summary,
        }
        with log_file.open("w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)

    return original_count, merged_count


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Merges duplicate contact records from CSV files using fuzzy " + "matching."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-i",
        "--input-file",
        required=True,
        type=Path,
        help="Path to input CSV file",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        required=True,
        type=Path,
        help="Path to output CSV file",
    )
    parser.add_argument("--name-col", help="Header name of contact name column")
    parser.add_argument("--email-col", help="Header name of email column")
    parser.add_argument("--phone-col", help="Header name of phone column")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Fuzzy match similarity threshold (0.0 to 1.0). Default: 0.85",
    )
    parser.add_argument(
        "--strategy",
        choices=["prefer_longest", "prefer_non_null"],
        default="prefer_longest",
        help=(
            "Conflict resolution strategy for merging values. "
            "Default: 'prefer_longest'"
        ),
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Path to write JSON merge report and cluster breakdown",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    try:
        orig, merged = process_merge_csv(
            input_file=parsed.input_file,
            output_file=parsed.output_file,
            name_col=parsed.name_col,
            email_col=parsed.email_col,
            phone_col=parsed.phone_col,
            threshold=parsed.threshold,
            strategy=parsed.strategy,
            log_file=parsed.log_file,
        )
        print("Duplicate contact merger complete.")
        print(f"  Original records: {orig}")
        print(f"  Merged records: {merged}")
        print(f"  Duplicates removed: {orig - merged}")
        print(f"Merged output written to: {parsed.output_file}")
        if parsed.log_file:
            print(f"Merge audit log saved to: {parsed.log_file}")
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

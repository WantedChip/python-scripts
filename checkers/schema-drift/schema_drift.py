#!/usr/bin/env python3
"""Schema Drift.

Compares two JSON files or API responses over time to identify schema changes:
keys added, keys removed, changed types, and nullability shifts.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict


# pylint: disable=too-many-nested-blocks
def build_schema(data: Any, path: str = "") -> Dict[str, Dict[str, Any]]:
    """Recursively traverse a JSON structure to map all keys and types."""
    schema = {}

    if data is None:
        schema[path] = {"type": "null", "nullable": True}
        return schema

    tname = type(data).__name__

    if isinstance(data, dict):
        schema[path or "/"] = {"type": "object", "nullable": False}
        for k, v in data.items():
            child_path = f"{path}/{k}" if path else f"/{k}"
            schema.update(build_schema(v, child_path))
    elif isinstance(data, list):
        schema[path or "/"] = {"type": "array", "nullable": False}
        if data:
            # Analyze elements to merge schemas
            list_schema = {}
            for item in data:
                # Merge signatures
                item_schema = build_schema(item, path)
                for item_path, item_meta in item_schema.items():
                    if item_path not in list_schema:
                        list_schema[item_path] = item_meta
                    else:
                        # If type differs, we mark as Union or mixed
                        if list_schema[item_path]["type"] != item_meta["type"]:
                            list_schema[item_path]["type"] = "mixed"
                        if item_meta.get("nullable"):
                            list_schema[item_path]["nullable"] = True
            schema.update(list_schema)
    else:
        schema[path] = {"type": tname, "nullable": False}

    return schema


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare two JSON structures to identify schema differences and drifts."
        )
    )
    parser.add_argument("schema_a", help="Initial JSON snapshot file path.")
    parser.add_argument(
        "schema_b", help="Target/latest JSON snapshot file path to check."
    )

    args = parser.parse_args()

    path_a = os.path.abspath(args.schema_a)
    path_b = os.path.abspath(args.schema_b)

    if not os.path.exists(path_a) or not os.path.exists(path_b):
        print("Error: One or both JSON snapshot files not found.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(path_a, "r", encoding="utf-8") as f:
            data_a = json.load(f)
        with open(path_b, "r", encoding="utf-8") as f:
            data_b = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error parsing JSON file contents: {e}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("SCHEMA DRIFT: API SCHEMAS COMPARATOR")
    print("========================================================================")
    print(f"Snapshot A: {path_a}")
    print(f"Snapshot B: {path_b}")
    print("Extracting object structures and checking differences...")
    print("-" * 80)

    # Build schemas
    schema_a = build_schema(data_a)
    schema_b = build_schema(data_b)

    drifts = []

    # 1. Check for removed keys or type changes
    for path, meta_a in schema_a.items():
        if path not in schema_b:
            drifts.append(
                {
                    "path": path,
                    "type": "Key Removed",
                    "old": meta_a["type"],
                    "new": "Missing",
                }
            )
        else:
            meta_b = schema_b[path]
            # Check type mismatch
            if (
                meta_a["type"] != meta_b["type"]
                and meta_a["type"] != "null"
                and meta_b["type"] != "null"
            ):
                drifts.append(
                    {
                        "path": path,
                        "type": "Type Mutation",
                        "old": meta_a["type"],
                        "new": meta_b["type"],
                    }
                )
            # Check nullability
            elif meta_a["nullable"] != meta_b["nullable"]:
                drifts.append(
                    {
                        "path": path,
                        "type": "Nullability Shift",
                        "old": "Non-nullable" if not meta_a["nullable"] else "Nullable",
                        "new": "Nullable" if meta_b["nullable"] else "Non-nullable",
                    }
                )

    # 2. Check for added keys
    for path, meta_b in schema_b.items():
        if path not in schema_a:
            drifts.append(
                {
                    "path": path,
                    "type": "Key Added",
                    "old": "Missing",
                    "new": meta_b["type"],
                }
            )

    if not drifts:
        print("\n[+] Success: JSON schemas match exactly. No drifts detected.")
        sys.exit(0)

    # Sort drifts: Removed first, then Type Mutation, then Added
    drifts.sort(key=lambda x: x["type"])

    print(f"\n[!] Discovered {len(drifts)} schema drift events:")
    print("=" * 80)
    print(
        f"{'FIELD PATH':<35} | {'DRIFT TYPE':<18} | {'MACHINE A':<11} | {'MACHINE B'}"
    )
    print("-" * 80)
    for d in drifts:
        print(f"{d['path'][:35]:<35} | {d['type']:<18} | {d['old']:<11} | {d['new']}")
    print("=" * 80)


if __name__ == "__main__":
    main()

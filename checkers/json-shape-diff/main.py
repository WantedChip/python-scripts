"""JSON Shape Diff CLI Tool.

Extracts recursive structural schemas from complex JSON datasets and performs
structural diffing (detecting added/missing fields, type mismatches, nullability
changes, and list element shape variations).
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-return-statements

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def get_type_name(val: Any, strict_numbers: bool = False) -> str:
    """Determine schema type name for a primitive or complex Python object.

    Args:
        val: Input data value.
        strict_numbers: If False, treats int and float both as 'number'.

    Returns:
        Type name string ('str', 'int', 'float', 'number', 'bool',
        'null', 'dict', 'list').
    """
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "bool"
    if isinstance(val, int):
        return "int" if strict_numbers else "number"
    if isinstance(val, float):
        return "float" if strict_numbers else "number"
    if isinstance(val, str):
        return "str"
    if isinstance(val, dict):
        return "dict"
    if isinstance(val, list):
        return "list"
    return type(val).__name__


def extract_shape(
    data: Any,
    max_depth: int = 100,
    current_depth: int = 0,
    strict_numbers: bool = False,
) -> Dict[str, Any]:
    """Recursively extract structural schema shape from JSON data.

    Args:
        data: Parsed JSON data.
        max_depth: Maximum recursion depth.
        current_depth: Current depth in recursion.
        strict_numbers: Whether to differentiate int and float.

    Returns:
        Dictionary representation of schema shape.
    """
    type_name = get_type_name(data, strict_numbers=strict_numbers)

    if current_depth >= max_depth:
        return {"type": "max_depth_exceeded", "nullable": False}

    if type_name in ("str", "int", "float", "number", "bool"):
        return {"type": type_name, "nullable": False}

    if type_name == "null":
        return {"type": "null", "nullable": True}

    if type_name == "dict":
        properties: Dict[str, Any] = {}
        for key, val in data.items():
            properties[key] = extract_shape(
                val,
                max_depth=max_depth,
                current_depth=current_depth + 1,
                strict_numbers=strict_numbers,
            )
        return {"type": "dict", "nullable": False, "properties": properties}

    if type_name == "list":
        if not data:
            empty_elem = {"type": "unknown", "nullable": False}
            return {"type": "list", "nullable": False, "element_shape": empty_elem}

        element_shapes = [
            extract_shape(
                elem,
                max_depth=max_depth,
                current_depth=current_depth + 1,
                strict_numbers=strict_numbers,
            )
            for elem in data
        ]
        merged_shape = element_shapes[0]
        for next_shape in element_shapes[1:]:
            merged_shape = merge_shapes(merged_shape, next_shape)

        return {"type": "list", "nullable": False, "element_shape": merged_shape}

    return {"type": "unknown", "nullable": False}


def merge_shapes(shape1: Dict[str, Any], shape2: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two structural shapes to handle polymorphic lists or union types.

    Args:
        shape1: First shape dictionary.
        shape2: Second shape dictionary.

    Returns:
        Merged shape dictionary.
    """
    if shape1["type"] == "null":
        merged = dict(shape2)
        merged["nullable"] = True
        return merged
    if shape2["type"] == "null":
        merged = dict(shape1)
        merged["nullable"] = True
        return merged

    if shape1["type"] != shape2["type"]:
        types_set: Set[str] = set()

        for s in (shape1, shape2):
            if s["type"] == "union":
                types_set.update(s.get("union_types", []))
            else:
                types_set.add(s["type"])

        is_nullable = shape1.get("nullable", False) or shape2.get("nullable", False)
        return {
            "type": "union",
            "nullable": is_nullable,
            "union_types": sorted(list(types_set)),
        }

    is_nullable = shape1.get("nullable", False) or shape2.get("nullable", False)

    if shape1["type"] == "dict":
        props1 = shape1.get("properties", {})
        props2 = shape2.get("properties", {})
        all_keys = set(props1.keys()).union(set(props2.keys()))
        merged_props = {}

        for k in all_keys:
            if k in props1 and k in props2:
                merged_props[k] = merge_shapes(props1[k], props2[k])
            elif k in props1:
                prop_copy = dict(props1[k])
                prop_copy["nullable"] = True
                merged_props[k] = prop_copy
            else:
                prop_copy = dict(props2[k])
                prop_copy["nullable"] = True
                merged_props[k] = prop_copy

        return {"type": "dict", "nullable": is_nullable, "properties": merged_props}

    if shape1["type"] == "list":
        elem1 = shape1.get("element_shape", {"type": "unknown", "nullable": False})
        elem2 = shape2.get("element_shape", {"type": "unknown", "nullable": False})
        return {
            "type": "list",
            "nullable": is_nullable,
            "element_shape": merge_shapes(elem1, elem2),
        }

    return {"type": shape1["type"], "nullable": is_nullable}


def is_path_ignored(path: str, ignore_patterns: Optional[List[str]]) -> bool:
    """Check if a given JSON path matches any ignore glob patterns.

    Args:
        path: JSON path string (e.g., '$.user.created_at').
        ignore_patterns: List of glob patterns.

    Returns:
        True if path is ignored, False otherwise.
    """
    if not ignore_patterns:
        return False

    for pattern in ignore_patterns:
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(
            path.replace("$.", ""), pattern
        ):
            return True
    return False


def diff_shapes(
    shape_a: Dict[str, Any],
    shape_b: Dict[str, Any],
    path: str = "$",
    ignore_patterns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Compare two shape structures recursively and return list of differences.

    Args:
        shape_a: Baseline shape dictionary.
        shape_b: Target shape dictionary.
        path: JSON path string.
        ignore_patterns: Path patterns to ignore.

    Returns:
        List of diff items with path, diff_type, baseline, target, and details.
    """
    diffs: List[Dict[str, Any]] = []

    if is_path_ignored(path, ignore_patterns):
        return diffs

    type_a = shape_a.get("type")
    type_b = shape_b.get("type")

    # Check nullability mismatch
    nullable_a = shape_a.get("nullable", False)
    nullable_b = shape_b.get("nullable", False)
    if nullable_a != nullable_b and type_a == type_b:
        diffs.append(
            {
                "path": path,
                "diff_type": "NULLABILITY_MISMATCH",
                "baseline": f"type={type_a}, nullable={nullable_a}",
                "target": f"type={type_b}, nullable={nullable_b}",
                "detail": f"Nullability changed from {nullable_a} to {nullable_b}",
            }
        )

    # Check type mismatch
    if type_a != type_b:
        msg = f"Type mismatch: '{type_a}' in baseline vs '{type_b}' in target"
        diffs.append(
            {
                "path": path,
                "diff_type": "TYPE_MISMATCH",
                "baseline": f"{type_a} (nullable={nullable_a})",
                "target": f"{type_b} (nullable={nullable_b})",
                "detail": msg,
            }
        )
        return diffs

    # Dict property comparison
    if type_a == "dict":
        props_a = shape_a.get("properties", {})
        props_b = shape_b.get("properties", {})

        keys_a = set(props_a.keys())
        keys_b = set(props_b.keys())

        # Missing keys in target
        for k in sorted(keys_a - keys_b):
            child_path = f"{path}.{k}"
            if not is_path_ignored(child_path, ignore_patterns):
                msg_missing = f"Field '{k}' present in baseline but missing in target"
                diffs.append(
                    {
                        "path": child_path,
                        "diff_type": "MISSING_FIELD",
                        "baseline": f"key={k} ({props_a[k].get('type')})",
                        "target": "ABSENT",
                        "detail": msg_missing,
                    }
                )

        # Added keys in target
        for k in sorted(keys_b - keys_a):
            child_path = f"{path}.{k}"
            if not is_path_ignored(child_path, ignore_patterns):
                msg_added = f"Field '{k}' missing in baseline but added in target"
                diffs.append(
                    {
                        "path": child_path,
                        "diff_type": "ADDED_FIELD",
                        "baseline": "ABSENT",
                        "target": f"key={k} ({props_b[k].get('type')})",
                        "detail": msg_added,
                    }
                )

        # Common keys diffing
        for k in sorted(keys_a.intersection(keys_b)):
            child_path = f"{path}.{k}"
            diffs.extend(
                diff_shapes(
                    props_a[k],
                    props_b[k],
                    path=child_path,
                    ignore_patterns=ignore_patterns,
                )
            )

    # List element shape comparison
    elif type_a == "list":
        elem_a = shape_a.get("element_shape", {})
        elem_b = shape_b.get("element_shape", {})
        diffs.extend(
            diff_shapes(
                elem_a,
                elem_b,
                path=f"{path}[*]",
                ignore_patterns=ignore_patterns,
            )
        )

    return diffs


def format_text_report(diffs: List[Dict[str, Any]], file_a: str, file_b: str) -> str:
    """Format structural diffs into human-readable text output.

    Args:
        diffs: List of diff dictionaries.
        file_a: Path to baseline file.
        file_b: Path to target file.

    Returns:
        Formatted string output.
    """
    lines = [
        "============================================================",
        " JSON SHAPE STRUCTURAL DIFF REPORT",
        "============================================================",
        f" Baseline (A): {file_a}",
        f" Target   (B): {file_b}",
        f" Total Structural Differences Found: {len(diffs)}",
        "------------------------------------------------------------",
    ]

    if not diffs:
        lines.append(" SUCCESS: JSON structures match perfectly (No shape drift).")
        return "\n".join(lines)

    counts: Dict[str, int] = {}
    for d in diffs:
        dt = d["diff_type"]
        counts[dt] = counts.get(dt, 0) + 1

    lines.append(" Summary of Differences:")
    for dt, count in sorted(counts.items()):
        lines.append(f"   - {dt:22s}: {count}")
    lines.append("------------------------------------------------------------")

    for idx, d in enumerate(diffs, 1):
        lines.extend(
            [
                f"[{idx}] Path: {d['path']}",
                f"    Type    : {d['diff_type']}",
                f"    Baseline: {d['baseline']}",
                f"    Target  : {d['target']}",
                f"    Detail  : {d['detail']}",
                "",
            ]
        )

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for JSON shape diff CLI."""
    parser = argparse.ArgumentParser(
        description="Compare two JSON files structurally (schema shape diffing)."
    )
    parser.add_argument("file_a", help="Path to baseline JSON file.")
    parser.add_argument("file_b", help="Path to target JSON file.")
    parser.add_argument(
        "-o", "--output", help="Output report file path (defaults to stdout)."
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--ignore",
        nargs="*",
        help="JSON path glob patterns to ignore (e.g., '$.meta.*').",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=100,
        help="Maximum depth for nested object analysis.",
    )
    parser.add_argument(
        "--strict-numbers",
        action="store_true",
        help="Strictly distinguish between int and float types.",
    )

    args = parser.parse_args(argv)

    path_a = Path(args.file_a)
    path_b = Path(args.file_b)

    if not path_a.is_file():
        print(f"Error: Baseline file not found: {args.file_a}", file=sys.stderr)
        return 1

    if not path_b.is_file():
        print(f"Error: Target file not found: {args.file_b}", file=sys.stderr)
        return 1

    try:
        data_a = json.loads(path_a.read_text(encoding="utf-8"))
        data_b = json.loads(path_b.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error parsing JSON file: {exc}", file=sys.stderr)
        return 1

    shape_a = extract_shape(
        data_a,
        max_depth=args.max_depth,
        strict_numbers=args.strict_numbers,
    )
    shape_b = extract_shape(
        data_b,
        max_depth=args.max_depth,
        strict_numbers=args.strict_numbers,
    )

    diffs = diff_shapes(shape_a, shape_b, ignore_patterns=args.ignore)

    if args.format == "json":
        report_data = {
            "baseline_file": str(path_a),
            "target_file": str(path_b),
            "diff_count": len(diffs),
            "differences": diffs,
        }
        output_content = json.dumps(report_data, indent=2)
    else:
        output_content = format_text_report(diffs, str(path_a), str(path_b))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_content, encoding="utf-8")
        print(f"Structural diff report written to: {args.output}")
    else:
        print(output_content)

    return 0 if not diffs else 2


if __name__ == "__main__":
    sys.exit(main())

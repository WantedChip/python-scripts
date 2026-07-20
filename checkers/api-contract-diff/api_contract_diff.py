#!/usr/bin/env python3
"""API Contract Diff — Compare two API versions and report breaking changes.

Validates OpenAPI/Swagger specifications for backward compatibility.
Detects breaking changes in paths, HTTP methods, parameters, request/response
schemas, status codes, and enums.
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Set, Tuple

import yaml  # type: ignore[import-untyped]

# Set up logger
logger = logging.getLogger("api_contract_diff")


def setup_logging(verbose: bool) -> None:
    """Configure logger verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)


def load_spec(filepath: str) -> Dict[str, Any]:
    """Parse JSON or YAML spec file.

    Args:
        filepath: Path to the specification file.

    Returns:
        The parsed specification as a dictionary.
    """
    if not os.path.exists(filepath):
        logger.error("Spec file not found: %s", filepath)
        sys.exit(1)

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        if filepath.endswith((".yaml", ".yml")):
            data = yaml.safe_load(content)
        else:
            data = json.loads(content)
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to parse spec file %s: %s", filepath, err)
        sys.exit(1)

    if not isinstance(data, dict):
        logger.error("Invalid spec format in %s. Root must be a dict.", filepath)
        sys.exit(1)

    return data


def resolve_ref(spec: Dict[str, Any], ref: str) -> Any:
    """Resolve local JSON Reference (e.g. #/components/schemas/User)."""
    if not ref.startswith("#/"):
        return {}
    parts = ref.split("/")[1:]
    curr = spec
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            return {}
    return curr


def dereference(spec: Dict[str, Any], schema: Any) -> Any:
    """Recursively dereference a schema if it contains a $ref."""
    if isinstance(schema, dict):
        if "$ref" in schema:
            return dereference(spec, resolve_ref(spec, schema["$ref"]))
        return {k: dereference(spec, v) for k, v in schema.items()}
    if isinstance(schema, list):
        return [dereference(spec, item) for item in schema]
    return schema


def get_paths(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve paths dictionary from spec."""
    paths = spec.get("paths", {})
    return paths if isinstance(paths, dict) else {}


def get_methods(path_item: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve HTTP methods from path item, skipping parameters/ref keys."""
    valid_methods = {
        "get",
        "post",
        "put",
        "delete",
        "options",
        "head",
        "patch",
        "trace",
    }
    return {k: v for k, v in path_item.items() if k.lower() in valid_methods}


def get_parameters(
    op: Dict[str, Any], spec: Dict[str, Any]
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Retrieve operation parameters as a dict mapped by (name, in)."""
    params: Dict[Tuple[str, str], Dict[str, Any]] = {}
    raw_params = op.get("parameters", [])
    for param in raw_params:
        param = dereference(spec, param)
        if isinstance(param, dict) and "name" in param and "in" in param:
            params[(param["name"], param["in"])] = param
    return params


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches  # noqa: E501
def compare_schemas(
    old_spec: Dict[str, Any],
    new_spec: Dict[str, Any],
    old_schema: Any,
    new_schema: Any,
    path_ctx: str,
    is_response: bool,
) -> List[str]:
    """Recursively compare two schemas for breaking changes.

    Args:
        old_spec: Old spec root.
        new_spec: New spec root.
        old_schema: Old schema node.
        new_schema: New schema node.
        path_ctx: Path context for logs.
        is_response: True if comparing a response schema, False for request.

    Returns:
        List of breaking change warning strings.
    """
    warnings: List[str] = []
    old_schema = dereference(old_spec, old_schema)
    new_schema = dereference(new_spec, new_schema)

    if not isinstance(old_schema, dict) or not isinstance(new_schema, dict):
        return warnings

    old_type = old_schema.get("type")
    new_type = new_schema.get("type")

    # 1. Type mismatch
    if old_type and new_type and old_type != new_type:
        warnings.append(f"{path_ctx}: Type changed from '{old_type}' to '{new_type}'.")
        return warnings

    # 2. Object properties comparison
    if old_type == "object" or "properties" in old_schema or "properties" in new_schema:
        old_props = old_schema.get("properties", {})
        new_props = new_schema.get("properties", {})
        old_req: Set[str] = set(old_schema.get("required", []))
        new_req: Set[str] = set(new_schema.get("required", []))

        # Check response body changes
        if is_response:
            # Removed fields from response is breaking
            for prop in old_props:
                if prop not in new_props:
                    warnings.append(f"{path_ctx}: Removed response field '{prop}'.")
            # Response field changed from optional to required is not breaking
            # but required to optional IS breaking (client expects it)
            for prop in old_props:
                if prop in old_req and prop not in new_req and prop in new_props:
                    warnings.append(
                        f"{path_ctx}: Response field '{prop}' changed from "
                        "required to optional."
                    )
        else:
            # Request body changes
            # Added required fields to request body is breaking
            for prop in new_props:
                if prop in new_req and prop not in old_req:
                    warnings.append(
                        f"{path_ctx}: Added required request field '{prop}'."
                    )

        # Recursively compare shared properties
        for prop in old_props:
            if prop in new_props:
                warnings.extend(
                    compare_schemas(
                        old_spec,
                        new_spec,
                        old_props[prop],
                        new_props[prop],
                        f"{path_ctx} -> {prop}",
                        is_response,
                    )
                )

    # 3. Array items comparison
    if old_type == "array" or "items" in old_schema or "items" in new_schema:
        old_items = old_schema.get("items")
        new_items = new_schema.get("items")
        if old_items and new_items:
            warnings.extend(
                compare_schemas(
                    old_spec,
                    new_spec,
                    old_items,
                    new_items,
                    f"{path_ctx}[]",
                    is_response,
                )
            )

    # 4. Enums comparison
    old_enum = old_schema.get("enum")
    new_enum = new_schema.get("enum")
    if isinstance(old_enum, list) and isinstance(new_enum, list):
        old_enum_set = set(old_enum)
        new_enum_set = set(new_enum)
        if is_response:
            # Added enum values in response is breaking
            added = new_enum_set - old_enum_set
            if added:
                warnings.append(
                    f"{path_ctx}: Added values {list(added)} to response enum."
                )
        else:
            # Removed enum values in request is breaking (client request might fail)
            removed = old_enum_set - new_enum_set
            if removed:
                warnings.append(
                    f"{path_ctx}: Removed values {list(removed)} from request enum."
                )

    return warnings


# pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-nested-blocks  # noqa: E501
def compare_specs(old_spec: Dict[str, Any], new_spec: Dict[str, Any]) -> List[str]:
    """Compare two specs for backward compatibility.

    Args:
        old_spec: Root dictionary of the old spec.
        new_spec: Root dictionary of the new spec.

    Returns:
        List of breaking change descriptions.
    """
    breaking_changes: List[str] = []

    old_paths = get_paths(old_spec)
    new_paths = get_paths(new_spec)

    # 1. Compare Paths
    for path, old_item in old_paths.items():
        if path not in new_paths:
            breaking_changes.append(f"Removed endpoint: {path}")
            continue

        new_item = new_paths[path]
        old_methods = get_methods(old_item)
        new_methods = get_methods(new_item)

        # 2. Compare HTTP Methods
        for method, old_op in old_methods.items():
            if method not in new_methods:
                breaking_changes.append(f"Removed method: {method.upper()} on {path}")
                continue

            new_op = new_methods[method]
            ctx = f"{method.upper()} {path}"

            # 3. Compare Parameters
            old_params = get_parameters(old_op, old_spec)
            new_params = get_parameters(new_op, new_spec)

            for (p_name, p_in), old_param in old_params.items():
                if (p_name, p_in) not in new_params:
                    # Parameter removed
                    breaking_changes.append(
                        f"{ctx}: Removed parameter '{p_name}' in {p_in}."
                    )
                    continue

                new_param = new_params[(p_name, p_in)]
                old_req = old_param.get("required", False)
                new_req = new_param.get("required", False)

                # Optional changed to required is breaking
                if not old_req and new_req:
                    breaking_changes.append(
                        f"{ctx}: Parameter '{p_name}' in {p_in} changed from "
                        "optional to required."
                    )

                # Type checks on parameter schema
                old_schema = old_param.get("schema")
                new_schema = new_param.get("schema")
                if old_schema and new_schema:
                    breaking_changes.extend(
                        compare_schemas(
                            old_spec,
                            new_spec,
                            old_schema,
                            new_schema,
                            f"{ctx} (parameter '{p_name}')",
                            is_response=False,
                        )
                    )

            # Check if any new parameter is required but wasn't present before
            for (p_name, p_in), new_param in new_params.items():
                if (p_name, p_in) not in old_params:
                    if new_param.get("required", False):
                        breaking_changes.append(
                            f"{ctx}: Added new required parameter '{p_name}' in {p_in}."
                        )

            # 4. Compare Request Bodies
            old_req_body = old_op.get("requestBody")
            new_req_body = new_op.get("requestBody")

            if old_req_body and not new_req_body:
                pass
            elif not old_req_body and new_req_body:
                new_req_body = dereference(new_spec, new_req_body)
                if new_req_body.get("required", False):
                    breaking_changes.append(f"{ctx}: Added required request body.")
            elif old_req_body and new_req_body:
                old_req_body = dereference(old_spec, old_req_body)
                new_req_body = dereference(new_spec, new_req_body)
                old_req = old_req_body.get("required", False)
                new_req = new_req_body.get("required", False)
                if not old_req and new_req:
                    breaking_changes.append(
                        f"{ctx}: Request body changed from optional to required."
                    )

                # Compare request schemas under content-types
                old_content = old_req_body.get("content", {})
                new_content = new_req_body.get("content", {})
                for mt in old_content:
                    if mt in new_content:
                        old_sh = old_content[mt].get("schema")
                        new_sh = new_content[mt].get("schema")
                        if old_sh and new_sh:
                            breaking_changes.extend(
                                compare_schemas(
                                    old_spec,
                                    new_spec,
                                    old_sh,
                                    new_sh,
                                    f"{ctx} (request body {mt})",
                                    is_response=False,
                                )
                            )

            # 5. Compare Responses
            old_responses = old_op.get("responses", {})
            new_responses = new_op.get("responses", {})

            for status, old_resp in old_responses.items():
                # Removed successful status code is breaking
                if status.startswith("2") and status not in new_responses:
                    breaking_changes.append(
                        f"{ctx}: Removed successful status code {status}."
                    )
                    continue

                if status in new_responses:
                    old_resp = dereference(old_spec, old_resp)
                    new_resp = dereference(new_spec, new_responses[status])

                    old_content = old_resp.get("content", {})
                    new_content = new_resp.get("content", {})

                    for mt in old_content:
                        if mt in new_content:
                            old_sh = old_content[mt].get("schema")
                            new_sh = new_content[mt].get("schema")
                            if old_sh and new_sh:
                                breaking_changes.extend(
                                    compare_schemas(
                                        old_spec,
                                        new_spec,
                                        old_sh,
                                        new_sh,
                                        f"{ctx} (response {status} {mt})",
                                        is_response=True,
                                    )
                                )

    return breaking_changes


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="api-contract-diff: Audits compatibility between two API contracts."
    )
    parser.add_argument("old_spec", help="Path to the reference spec file (JSON/YAML)")
    parser.add_argument("new_spec", help="Path to the new spec file (JSON/YAML)")
    parser.add_argument(
        "--format",
        choices=["text", "markdown"],
        default="text",
        help="Report format",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable detailed logs"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    logger.info("Loading reference spec: %s", args.old_spec)
    old_spec_data = load_spec(args.old_spec)

    logger.info("Loading new spec: %s", args.new_spec)
    new_spec_data = load_spec(args.new_spec)

    logger.info("Analyzing backward compatibility...")
    changes = compare_specs(old_spec_data, new_spec_data)

    if not changes:
        print("No breaking changes detected. Backward compatibility verified.")
        sys.exit(0)

    # Output report
    if args.format == "markdown":
        print("# API Contract breaking changes report\n")
        print(f"Detected **{len(changes)}** breaking change(s):\n")
        for idx, change in enumerate(changes, 1):
            print(f"{idx}. ⚠️ {change}")
    else:
        print("=" * 80)
        print("                      API CONTRACT BREAKING CHANGES")
        print("=" * 80)
        for idx, change in enumerate(changes, 1):
            print(f"[{idx}] {change}")
        print("=" * 80)

    sys.exit(1)


if __name__ == "__main__":
    main()

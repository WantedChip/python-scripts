"""JSON Formatter CLI.

Pretty-print, minify, query (jq-style path keys), and validate JSON files.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=too-many-return-statements

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# ANSI Color Codes
COLOR_RESET = "\033[0m"
COLOR_KEY = "\033[34;1m"  # Bold Blue
COLOR_STRING = "\033[32m"  # Green
COLOR_NUMBER = "\033[33m"  # Yellow
COLOR_BOOL = "\033[35m"  # Magenta
COLOR_NULL = "\033[31m"  # Red


class JSONQueryEngine:
    """Parses and executes queries on JSON objects."""

    @staticmethod
    def parse_path(query_path: str) -> List[Union[str, int]]:
        """Parses query paths such as 'users[0].name' or '.store.item.2'."""
        clean_path = query_path.strip()
        if clean_path.startswith("."):
            clean_path = clean_path[1:]

        if not clean_path:
            return []

        tokens: List[Union[str, int]] = []
        # Pattern matches words or array indices [n]
        raw_parts = re.split(r"\.|\b(?=\[)", clean_path)

        for part in raw_parts:
            if not part:
                continue
            # Match bracket indices like [0] or [12]
            bracket_matches = re.findall(r"\[(\d+)\]", part)
            key_name = re.sub(r"\[\d+\]", "", part)

            if key_name:
                tokens.append(key_name)
            for index_str in bracket_matches:
                tokens.append(int(index_str))

        return tokens

    @classmethod
    def execute_query(cls, data: Any, query_path: str) -> Tuple[bool, Any]:
        """Navigates JSON structure following parsed path tokens.

        Returns (success: bool, value: Any).
        """
        tokens = cls.parse_path(query_path)
        current = data

        for token in tokens:
            if isinstance(token, str):
                if isinstance(current, dict) and token in current:
                    current = current[token]
                else:
                    return False, f"Key '{token}' not found in target dict."
            elif isinstance(token, int):
                if isinstance(current, list) and 0 <= token < len(current):
                    current = current[token]
                else:
                    arr_len = len(current) if isinstance(current, list) else 0
                    msg = f"Index [{token}] out of bounds for array length {arr_len}."
                    return False, msg

        return True, current


class JSONFormatter:
    """Pretty prints, colors, minifies, and formats JSON data."""

    @staticmethod
    def minify(data: Any) -> str:
        """Minifies JSON object to compact single line."""
        return json.dumps(data, separators=(",", ":"))

    @staticmethod
    def pretty_print(data: Any, indent: int = 2, colorize: bool = True) -> str:
        """Pretty prints JSON object with optional ANSI color highlighting."""
        raw_json = json.dumps(data, indent=indent)
        if not colorize:
            return raw_json

        return JSONFormatter.colorize_json(raw_json)

    @staticmethod
    def colorize_json(json_str: str) -> str:
        """Applies ANSI colors to keys, strings, numbers, booleans, and nulls."""
        lines = json_str.split("\n")
        colored_lines = []
        for line in lines:
            # Match key: value patterns
            colon_idx = line.find(":")
            if colon_idx != -1 and line[:colon_idx].strip().startswith('"'):
                key_part = line[:colon_idx]
                val_part = line[colon_idx + 1 :]  # noqa: E203

                colored_key = f"{COLOR_KEY}{key_part}{COLOR_RESET}"

                # Color val_part
                v_trimmed = val_part.strip().rstrip(",")
                comma = "," if val_part.strip().endswith(",") else ""

                if v_trimmed.startswith('"'):
                    colored_val = f"{COLOR_STRING}{v_trimmed}{COLOR_RESET}"
                elif v_trimmed in ("true", "false"):
                    colored_val = f"{COLOR_BOOL}{v_trimmed}{COLOR_RESET}"
                elif v_trimmed == "null":
                    colored_val = f"{COLOR_NULL}{v_trimmed}{COLOR_RESET}"
                elif re.match(r"^-?\d+(\.\d+)?$", v_trimmed):
                    colored_val = f"{COLOR_NUMBER}{v_trimmed}{COLOR_RESET}"
                else:
                    colored_val = v_trimmed

                indent_prefix = line[: len(line) - len(line.lstrip())]
                formatted_line = f"{indent_prefix}{colored_key}:{colored_val}{comma}"
                colored_lines.append(formatted_line)
            else:
                colored_lines.append(line)

        return "\n".join(colored_lines)


class JSONSchemaValidator:
    """Basic JSON schema structure validator."""

    @staticmethod
    def validate(data: Any, schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validates JSON data against basic schema definitions."""
        errors: List[str] = []

        expected_type = schema.get("type")
        if expected_type:
            type_map: Dict[str, Union[type, Tuple[type, ...]]] = {
                "object": dict,
                "array": list,
                "string": str,
                "number": (int, float),
                "integer": int,
                "boolean": bool,
            }
            target_class = type_map.get(expected_type)
            if target_class and not isinstance(data, target_class):
                got_type = type(data).__name__
                msg = (
                    f"Root data type mismatch. Expected '{expected_type}', "
                    f"got '{got_type}'."
                )
                errors.append(msg)
                return False, errors

        if isinstance(data, dict):
            required_keys = schema.get("required", [])
            for r_key in required_keys:
                if r_key not in data:
                    errors.append(f"Missing required property key '{r_key}'.")

            properties = schema.get("properties", {})
            for key, prop_schema in properties.items():
                if key in data:
                    _, prop_errors = JSONSchemaValidator.validate(
                        data[key], prop_schema
                    )
                    for err in prop_errors:
                        errors.append(f"Property '{key}': {err}")

        return len(errors) == 0, errors


def load_json_source(source: str) -> Tuple[bool, Any]:
    """Loads JSON data from file path or inline JSON string."""
    try:
        if source.strip().startswith("{") or source.strip().startswith("["):
            return True, json.loads(source)
        with open(source, "r", encoding="utf-8") as f:
            return True, json.load(f)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        return False, f"Failed to parse JSON: {e}"


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="JSON Formatter CLI")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # Format command
    format_parser = subparsers.add_parser("format", help="Pretty print JSON")
    format_parser.add_argument("source", help="JSON file path or raw string")
    format_parser.add_argument(
        "--indent", type=int, default=2, help="Indent space count"
    )
    format_parser.add_argument(
        "--no-color", action="store_true", help="Disable syntax color"
    )

    # Minify command
    minify_parser = subparsers.add_parser("minify", help="Minify JSON")
    minify_parser.add_argument("source", help="JSON file path or raw string")

    # Query command
    query_parser = subparsers.add_parser("query", help="Query JSON value by path key")
    query_parser.add_argument("source", help="JSON file path or raw string")
    query_parser.add_argument("path", help="Query path key (e.g. 'users[0].name')")
    query_parser.add_argument(
        "--no-color", action="store_true", help="Disable color output"
    )

    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate JSON against schema")
    val_parser.add_argument("source", help="JSON file path or raw string")
    val_parser.add_argument("schema", help="Schema file path or raw JSON string")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.command == "format":
        success, data_or_err = load_json_source(parsed.source)
        if not success:
            print(f"Error: {data_or_err}")
            return 1
        formatted = JSONFormatter.pretty_print(
            data_or_err, indent=parsed.indent, colorize=not parsed.no_color
        )
        print(formatted)

    elif parsed.command == "minify":
        success, data_or_err = load_json_source(parsed.source)
        if not success:
            print(f"Error: {data_or_err}")
            return 1
        minified = JSONFormatter.minify(data_or_err)
        print(minified)

    elif parsed.command == "query":
        success, data_or_err = load_json_source(parsed.source)
        if not success:
            print(f"Error: {data_or_err}")
            return 1

        q_success, q_res = JSONQueryEngine.execute_query(data_or_err, parsed.path)
        if not q_success:
            print(f"Query Error: {q_res}")
            return 1

        if isinstance(q_res, (dict, list)):
            print(JSONFormatter.pretty_print(q_res, colorize=not parsed.no_color))
        else:
            print(q_res)

    elif parsed.command == "validate":
        success, data_or_err = load_json_source(parsed.source)
        if not success:
            print(f"Data Error: {data_or_err}")
            return 1

        s_success, schema_or_err = load_json_source(parsed.schema)
        if not s_success:
            print(f"Schema Error: {schema_or_err}")
            return 1

        is_valid, errors = JSONSchemaValidator.validate(data_or_err, schema_or_err)
        if is_valid:
            print("Validation PASSED! JSON conforms to specified schema.")
        else:
            print("Validation FAILED with errors:")
            for err in errors:
                print(f" - {err}")
            return 1

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())

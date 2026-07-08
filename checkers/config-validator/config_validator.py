"""JSON/YAML Config Validator.

A CLI tool to validate JSON and YAML configuration files against JSON Schemas,
producing highly readable error messages with line, column, and context snippets.
"""

import argparse
import json
import logging
import os
import re
import sys
from typing import Any, Dict, Generator, List, Tuple, Union

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("config-validator")


class JSONPositionParser:
    """A recursive descent JSON parser that tracks the line and column of every node.

    Also detects duplicate keys which the standard json module permits but are
    often configuration bugs.
    """

    def __init__(self, text: str) -> None:
        """Initializes the parser with the input text."""
        self.text = text
        self.pos = 0
        self.length = len(text)
        self.positions: Dict[Tuple[Union[str, int], ...], Tuple[int, int]] = {}

    def _get_line_col(self, index: int) -> Tuple[int, int]:
        """Calculates 1-indexed line and column numbers for a given index."""
        lines = self.text[:index].split("\n")
        line = len(lines)
        col = len(lines[-1]) + 1
        return line, col

    def parse(self) -> Tuple[Any, Dict[Tuple[Union[str, int], ...], Tuple[int, int]]]:
        """Parses the text and returns the data and position map."""
        self.pos = 0
        self.positions = {}
        self._skip_whitespace()
        if self.pos >= self.length:
            raise ValueError("Empty input")
        val = self._parse_value(())
        self._skip_whitespace()
        if self.pos < self.length:
            line, col = self._get_line_col(self.pos)
            raise ValueError(
                f"Unexpected character {self.text[self.pos]!r} at line {line}, col {col}"
            )
        return val, self.positions

    def _skip_whitespace(self) -> None:
        """Skips whitespace characters."""
        while self.pos < self.length and self.text[self.pos] in " \t\n\r":
            self.pos += 1

    def _parse_value(self, path: Tuple[Union[str, int], ...]) -> Any:
        """Parses a value at the given path."""
        self._skip_whitespace()
        if self.pos >= self.length:
            raise ValueError("Unexpected end of input")

        start_index = self.pos
        line, col = self._get_line_col(start_index)
        self.positions[path] = (line, col)

        char = self.text[self.pos]
        if char == "{":
            return self._parse_object(path)
        elif char == "[":
            return self._parse_array(path)
        elif char == '"':
            return self._parse_string()
        elif char in "-0123456789":
            return self._parse_number()
        elif self.text.startswith("true", self.pos):
            self.pos += 4
            return True
        elif self.text.startswith("false", self.pos):
            self.pos += 5
            return False
        elif self.text.startswith("null", self.pos):
            self.pos += 4
            return None
        else:
            raise ValueError(
                f"Unexpected character {char!r} at line {line}, col {col}"
            )

    def _parse_string(self) -> str:
        """Parses a double-quoted JSON string with escape sequence support."""
        if self.text[self.pos] != '"':
            raise ValueError("Expected string opening quote")
        self.pos += 1
        chars: List[str] = []
        while self.pos < self.length:
            char = self.text[self.pos]
            if char == '"':
                self.pos += 1
                return "".join(chars)
            elif char == "\\":
                if self.pos + 1 >= self.length:
                    raise ValueError("Unterminated escape sequence")
                next_char = self.text[self.pos + 1]
                if next_char == '"':
                    chars.append('"')
                elif next_char == "\\":
                    chars.append("\\")
                elif next_char == "/":
                    chars.append("/")
                elif next_char == "b":
                    chars.append("\b")
                elif next_char == "f":
                    chars.append("\f")
                elif next_char == "n":
                    chars.append("\n")
                elif next_char == "r":
                    chars.append("\r")
                elif next_char == "t":
                    chars.append("\t")
                elif next_char == "u":
                    hex_str = self.text[self.pos + 2 : self.pos + 6]
                    if len(hex_str) < 4:
                        raise ValueError("Invalid unicode escape")
                    chars.append(chr(int(hex_str, 16)))
                    self.pos += 4
                else:
                    chars.append(next_char)
                self.pos += 2
            else:
                chars.append(char)
                self.pos += 1
        raise ValueError("Unterminated string")

    def _parse_number(self) -> Union[int, float]:
        """Parses a JSON number using standard regex pattern."""
        match = re.match(
            r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", self.text[self.pos :]
        )
        if not match:
            line, col = self._get_line_col(self.pos)
            raise ValueError(f"Invalid number format at line {line}, col {col}")
        num_str = match.group(0)
        self.pos += len(num_str)
        if "." in num_str or "e" in num_str or "E" in num_str:
            return float(num_str)
        return int(num_str)

    def _parse_array(self, path: Tuple[Union[str, int], ...]) -> List[Any]:
        """Parses a JSON array, tracking indices in positions."""
        self.pos += 1  # skip '['
        result: List[Any] = []
        self._skip_whitespace()
        if self.pos < self.length and self.text[self.pos] == "]":
            self.pos += 1
            return result

        idx = 0
        while True:
            val = self._parse_value(path + (idx,))
            result.append(val)
            self._skip_whitespace()
            if self.pos >= self.length:
                raise ValueError("Unterminated array")
            char = self.text[self.pos]
            if char == "]":
                self.pos += 1
                break
            elif char == ",":
                self.pos += 1
                idx += 1
            else:
                line, col = self._get_line_col(self.pos)
                raise ValueError(
                    f"Expected ',' or ']' in array at line {line}, col {col}"
                )
        return result

    def _parse_object(
        self, path: Tuple[Union[str, int], ...]
    ) -> Dict[str, Any]:
        """Parses a JSON object, checking for duplicates and tracking key positions."""
        self.pos += 1  # skip '{'
        result: Dict[str, Any] = {}
        self._skip_whitespace()
        if self.pos < self.length and self.text[self.pos] == "}":
            self.pos += 1
            return result

        while True:
            self._skip_whitespace()
            start_key_idx = self.pos
            key_line, key_col = self._get_line_col(start_key_idx)

            if self.pos >= self.length or self.text[self.pos] != '"':
                raise ValueError(
                    f"Expected string key in object at line {key_line}, col {key_col}"
                )

            key = self._parse_string()
            self.positions[path + (key, "key")] = (key_line, key_col)

            self._skip_whitespace()
            if self.pos >= self.length or self.text[self.pos] != ":":
                line, col = self._get_line_col(self.pos)
                raise ValueError(
                    f"Expected ':' after key {key!r} at line {line}, col {col}"
                )
            self.pos += 1  # skip ':'

            val = self._parse_value(path + (key,))
            if key in result:
                raise ValueError(
                    f"Duplicate key {key!r} in object at line {key_line}, col {key_col}"
                )
            result[key] = val

            self._skip_whitespace()
            if self.pos >= self.length:
                raise ValueError("Unterminated object")
            char = self.text[self.pos]
            if char == "}":
                self.pos += 1
                break
            elif char == ",":
                self.pos += 1
            else:
                line, col = self._get_line_col(self.pos)
                raise ValueError(
                    f"Expected ',' or '}}' in object at line {line}, col {col}"
                )
        return result


def parse_yaml_with_positions(
    text: str,
) -> Tuple[Any, Dict[Tuple[Union[str, int], ...], Tuple[int, int]]]:
    """Parses a YAML string and constructs a position map for all elements.

    Detects duplicate keys in mapping structures.
    """
    loader = yaml.SafeLoader(text)
    try:
        node = loader.get_single_node()
    finally:
        loader.dispose()

    if node is None:
        return None, {}

    positions: Dict[Tuple[Union[str, int], ...], Tuple[int, int]] = {}

    def construct_and_track(node: yaml.Node, path: Tuple[Union[str, int], ...] = ()) -> Any:
        if node.start_mark:
            positions[path] = (node.start_mark.line + 1, node.start_mark.column + 1)

        if isinstance(node, ScalarNode):
            return loader.construct_object(node)
        elif isinstance(node, SequenceNode):
            result = []
            for idx, item_node in enumerate(node.value):
                val = construct_and_track(item_node, path + (idx,))
                result.append(val)
            return result
        elif isinstance(node, MappingNode):
            result: Dict[str, Any] = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node)
                if key_node.start_mark:
                    positions[path + (key, "key")] = (
                        key_node.start_mark.line + 1,
                        key_node.start_mark.column + 1,
                    )

                if key in result:
                    line = key_node.start_mark.line + 1
                    col = key_node.start_mark.column + 1
                    raise ValueError(
                        f"Duplicate key {key!r} in YAML mapping at line {line}, col {col}"
                    )

                val = construct_and_track(value_node, path + (key,))
                result[key] = val
            return result
        return None

    data = construct_and_track(node)
    return data, positions


def locate_error_position(
    error: Any, positions: Dict[Tuple[Union[str, int], ...], Tuple[int, int]]
) -> Tuple[int, int]:
    """Locates the line and column for a validation error using the position map."""
    path = tuple(error.absolute_path)

    # For required field error, error.absolute_path is the parent object path
    if error.validator == "required" and error.message:
        # Match error message like: "'port' is a required property"
        match = re.match(r"'([^']+)' is a required property", error.message)
        if match:
            missing_prop = match.group(1)
            # Try to point to where the missing key would belong
            key_path = path + (missing_prop, "key")
            if key_path in positions:
                return positions[key_path]

    # Try pointing directly to the invalid value
    if path in positions:
        return positions[path]

    # Try pointing to the key of that path
    if len(path) > 0:
        parent_path = path[:-1]
        last_key = path[-1]
        key_path = parent_path + (last_key, "key")
        if key_path in positions:
            return positions[key_path]

    # Try pointing to the parent path
    if len(path) > 0:
        parent_path = path[:-1]
        if parent_path in positions:
            return positions[parent_path]

    # Default to the top of the file
    return (1, 1)


def format_error_with_context(
    filename: str,
    file_content: str,
    line: int,
    col: int,
    message: str,
    validator: str,
    no_color: bool = False,
) -> str:
    """Formats a validation error with file context and standard compiler-like pointers."""
    lines = file_content.splitlines()
    total_lines = len(lines)

    # ANSI coloring configurations
    RED = "" if no_color else "\033[91m"
    BLUE = "" if no_color else "\033[94m"
    BOLD = "" if no_color else "\033[1m"
    RESET = "" if no_color else "\033[0m"

    result = []
    result.append(
        f"{RED}{BOLD}Validation Error [{validator}]{RESET}: {BOLD}{message}{RESET}"
    )
    result.append(f"  {BLUE}-->{RESET} {filename}:{line}:{col}")

    # Set snippet range (1 line before, target line, 1 line after)
    start_line = max(1, line - 1)
    end_line = min(total_lines, line + 1)
    width = len(str(end_line))

    result.append(f"   {BLUE}{' ' * width} |{RESET}")
    for l_num in range(start_line, end_line + 1):
        if l_num > total_lines:
            break
        l_content = lines[l_num - 1]
        if l_num == line:
            result.append(f" {BLUE}{l_num:>{width}} |{RESET} {l_content}")
            indent = " " * max(0, col - 1)
            result.append(
                f"   {BLUE}{' ' * width} |{RESET} {indent}{RED}^{RESET} {RED}{message}{RESET}"
            )
        else:
            result.append(f" {BLUE}{l_num:>{width}} |{RESET} {l_content}")
    result.append(f"   {BLUE}{' ' * width} |{RESET}")
    return "\n".join(result)


def parse_and_track(
    file_path: str, content: str
) -> Tuple[Any, Dict[Tuple[Union[str, int], ...], Tuple[int, int]]]:
    """Parses file contents based on extension, recording positions."""
    _, ext = os.path.splitext(file_path.lower())
    if ext == ".json":
        parser = JSONPositionParser(content)
        return parser.parse()
    elif ext in (".yaml", ".yml"):
        return parse_yaml_with_positions(content)
    else:
        # Fallback parsing (try JSON first, then YAML)
        try:
            parser = JSONPositionParser(content)
            return parser.parse()
        except ValueError:
            return parse_yaml_with_positions(content)


def load_schema(schema_path: str) -> Tuple[Any, str]:
    """Loads a schema file from the given path, returning the data and raw content."""
    with open(schema_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse schema (usually JSON, but could be YAML)
    try:
        data, _ = parse_and_track(schema_path, content)
        return data, content
    except Exception as e:
        raise RuntimeError(f"Failed to parse schema file {schema_path}: {e}") from e


def validate_config(
    schema_data: Any,
    config_path: str,
    fail_fast: bool = False,
    no_color: bool = False,
) -> List[str]:
    """Validates a single configuration file against a JSON Schema.

    Returns a list of formatted validation error strings.
    """
    import jsonschema
    from jsonschema.validators import validator_for

    formatted_errors = []

    # Read config file content
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return [f"Failed to read configuration file {config_path}: {e}"]

    # Parse config file content with position tracking
    try:
        data, positions = parse_and_track(config_path, content)
    except Exception as e:
        # Handle parse/syntax errors with line positions if possible
        line, col = 1, 1
        message = str(e)
        if hasattr(e, "problem_mark") and e.problem_mark:
            line = e.problem_mark.line + 1
            col = e.problem_mark.column + 1
        elif "line" in message and "col" in message:
            # Attempt to extract line and column from the error message
            match = re.search(r"line (\d+), col (\d+)", message)
            if match:
                line = int(match.group(1))
                col = int(match.group(2))

        return [
            format_error_with_context(
                config_path,
                content,
                line,
                col,
                message,
                "SyntaxError",
                no_color=no_color,
            )
        ]

    if data is None:
        return []

    # Choose validator based on schema rules
    try:
        validator_cls = validator_for(schema_data)
        validator = validator_cls(schema_data)
    except Exception as e:
        return [f"Invalid JSON Schema setup: {e}"]

    # Run validation
    errors = list(validator.iter_errors(data))
    for error in errors:
        line, col = locate_error_position(error, positions)
        formatted_errors.append(
            format_error_with_context(
                config_path,
                content,
                line,
                col,
                error.message,
                error.validator,
                no_color=no_color,
            )
        )
        if fail_fast:
            break

    return formatted_errors


def main() -> None:
    """The main entry point for the config validator CLI."""
    parser = argparse.ArgumentParser(
        description="JSON/YAML Config Validator with highly readable compilation errors."
    )
    parser.add_argument(
        "-s",
        "--schema",
        required=True,
        help="Path to the JSON/YAML Schema file to validate against.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit on the first validation error encountered.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output in formatting.",
    )
    parser.add_argument(
        "configs",
        nargs="+",
        help="One or more JSON/YAML configuration files to validate.",
    )

    args = parser.parse_args()

    # Verify files exist
    if not os.path.isfile(args.schema):
        logger.error("Schema file not found: %s", args.schema)
        sys.exit(2)

    for config_path in args.configs:
        if not os.path.isfile(config_path):
            logger.error("Config file not found: %s", config_path)
            sys.exit(2)

    # Load and validate the schema itself first
    try:
        schema_data, schema_content = load_schema(args.schema)
        from jsonschema.validators import validator_for

        validator_cls = validator_for(schema_data)
        validator_cls.check_schema(schema_data)
    except Exception as e:
        # If it's a validation error inside the schema itself, format it nicely!
        import jsonschema

        if isinstance(e, jsonschema.exceptions.SchemaError):
            # Parse the schema file again to track positions
            try:
                _, schema_positions = parse_and_track(args.schema, schema_content)
                line, col = locate_error_position(e, schema_positions)
                formatted_err = format_error_with_context(
                    args.schema,
                    schema_content,
                    line,
                    col,
                    e.message,
                    f"SchemaError: {e.validator}",
                    no_color=args.no_color,
                )
                print(formatted_err, file=sys.stderr)
            except Exception:
                logger.error("Schema is invalid: %s", e)
        else:
            logger.error("Failed to compile schema: %s", e)
        sys.exit(2)

    # Validate configuration files
    has_errors = False
    for config_path in args.configs:
        errors = validate_config(
            schema_data,
            config_path,
            fail_fast=args.fail_fast,
            no_color=args.no_color,
        )
        if errors:
            has_errors = True
            for err in errors:
                print(err, file=sys.stderr)
                print("-" * 60, file=sys.stderr)

    if has_errors:
        sys.exit(1)
    else:
        logger.info("All configuration files validated successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()

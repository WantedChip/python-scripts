"""Unit tests for the JSON/YAML Config Validator script."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent directory to sys.path to enable import of config_validator
# config-validator is a kebab-case directory, so we import config_validator directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config_validator import (  # noqa: E402
    JSONPositionParser,
    format_error_with_context,
    load_schema,
    locate_error_position,
    main,
    parse_and_track,
    parse_yaml_with_positions,
    validate_config,
)


def test_json_position_parser_valid() -> None:
    """Tests that the JSON position parser works for valid JSON files."""
    json_data = (
        "{\n"
        '  "name": "myapp",\n'
        '  "port": 8080,\n'
        '  "enabled": true,\n'
        '  "hosts": [\n'
        '    "localhost",\n'
        '    "127.0.0.1"\n'
        "  ]\n"
        "}"
    )
    parser = JSONPositionParser(json_data)
    data, positions = parser.parse()

    assert data == {
        "name": "myapp",
        "port": 8080,
        "enabled": True,
        "hosts": ["localhost", "127.0.0.1"],
    }

    # Verify positions (1-indexed)
    assert positions[()] == (1, 1)
    assert positions[("name",)] == (2, 11)
    assert positions[("port",)] == (3, 11)
    assert positions[("enabled",)] == (4, 14)
    assert positions[("hosts",)] == (5, 12)
    assert positions[("hosts", 0)] == (6, 5)
    assert positions[("hosts", 1)] == (7, 5)

    # Verify key positions
    assert positions[("name", "key")] == (2, 3)
    assert positions[("port", "key")] == (3, 3)
    assert positions[("enabled", "key")] == (4, 3)
    assert positions[("hosts", "key")] == (5, 3)


def test_json_position_parser_duplicate_key() -> None:
    """Tests that JSON position parser rejects duplicate keys."""
    json_data = '{\n  "port": 8080,\n  "port": 9090\n}'
    parser = JSONPositionParser(json_data)
    with pytest.raises(ValueError, match="Duplicate key 'port'"):
        parser.parse()


def test_json_position_parser_syntax_error() -> None:
    """Tests that JSON position parser raises ValueError on syntax errors."""
    json_data = '{\n  "port": 8080,\n  "name": "myapp"\n  "enabled": true\n}'
    parser = JSONPositionParser(json_data)
    with pytest.raises(ValueError, match="Expected ',' or '}'"):
        parser.parse()


def test_yaml_position_parser_valid() -> None:
    """Tests that the YAML position parser works for valid YAML."""
    yaml_data = (
        "name: myapp\n"
        "port: 8080\n"
        "features:\n"
        "  - oauth\n"
        "  - saml\n"
        "settings:\n"
        "  debug: true\n"
    )
    data, positions = parse_yaml_with_positions(yaml_data)

    assert data == {
        "name": "myapp",
        "port": 8080,
        "features": ["oauth", "saml"],
        "settings": {"debug": True},
    }

    # Verify positions
    assert positions[()] == (1, 1)
    assert positions[("name",)] == (1, 7)
    assert positions[("port",)] == (2, 7)
    assert positions[("features",)] == (4, 3)
    assert positions[("features", 0)] == (4, 5)
    assert positions[("features", 1)] == (5, 5)
    assert positions[("settings",)] == (7, 3)
    assert positions[("settings", "debug")] == (7, 10)


def test_yaml_position_parser_duplicate_key() -> None:
    """Tests that YAML position parser rejects duplicate keys."""
    yaml_data = "port: 8080\nport: 9090\n"
    with pytest.raises(ValueError, match="Duplicate key 'port'"):
        parse_yaml_with_positions(yaml_data)


def test_validate_config_success() -> None:
    """Tests validate_config when configuration meets schema."""
    schema = {
        "type": "object",
        "properties": {
            "port": {"type": "integer", "minimum": 1024},
            "host": {"type": "string"},
        },
        "required": ["port", "host"],
    }
    config = '{\n  "port": 8080,\n  "host": "localhost"\n}'

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp.write(config)
        tmp_name = tmp.name

    try:
        errors = validate_config(schema, tmp_name)
        assert len(errors) == 0
    finally:
        os.remove(tmp_name)


def test_validate_config_failure_type() -> None:
    """Tests validate_config when there is a type mismatch."""
    schema = {
        "type": "object",
        "properties": {
            "port": {"type": "integer"},
        },
    }
    config = '{\n  "port": "invalid-port"\n}'

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp.write(config)
        tmp_name = tmp.name

    try:
        errors = validate_config(schema, tmp_name, no_color=True)
        assert len(errors) == 1
        assert "Validation Error [type]" in errors[0]
        assert "config.json:2:11" in errors[0] or tmp_name in errors[0]
        assert "port" in errors[0]
    finally:
        os.remove(tmp_name)


def test_validate_config_failure_required() -> None:
    """Tests validate_config when a required property is missing."""
    schema = {
        "type": "object",
        "properties": {
            "port": {"type": "integer"},
            "host": {"type": "string"},
        },
        "required": ["port", "host"],
    }
    config = "port: 8080\n"

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
        tmp.write(config)
        tmp_name = tmp.name

    try:
        errors = validate_config(schema, tmp_name, no_color=True)
        assert len(errors) == 1
        assert "Validation Error [required]" in errors[0]
        # Required error points to parent mapping node (1, 1) or host: key (not present)
        assert "1:1" in errors[0] or tmp_name in errors[0]
    finally:
        os.remove(tmp_name)


def test_validate_config_syntax_error() -> None:
    """Tests validate_config handles syntactically invalid files gracefully."""
    schema = {"type": "object"}
    config = '{\n  "port": 8080,\n  "host": "localhost"\n  "enabled": true\n}'

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp.write(config)
        tmp_name = tmp.name

    try:
        errors = validate_config(schema, tmp_name, no_color=True)
        assert len(errors) == 1
        assert "Validation Error [SyntaxError]" in errors[0]
        assert "line 4" in errors[0] or "col" in errors[0]
    finally:
        os.remove(tmp_name)


def test_main_cli_success() -> None:
    """Tests CLI execution success with valid config and schema."""
    from config_validator import main

    schema = (
        "{\n"
        '  "type": "object",\n'
        '  "properties": {\n'
        '    "port": {"type": "integer"}\n'
        "  }\n"
        "}"
    )
    config = '{\n  "port": 8080\n}'

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as schema_file:
        schema_file.write(schema)
        schema_path = schema_file.name

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as config_file:
        config_file.write(config)
        config_path = config_file.name

    try:
        old_argv = sys.argv
        sys.argv = ["config_validator.py", "--schema", schema_path, config_path]
        try:
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
        finally:
            sys.argv = old_argv
    finally:
        os.remove(schema_path)
        os.remove(config_path)


def test_main_cli_failure() -> None:
    """Tests CLI execution failure with invalid config."""
    from config_validator import main

    schema = (
        "{\n"
        '  "type": "object",\n'
        '  "properties": {\n'
        '    "port": {"type": "integer"}\n'
        "  }\n"
        "}"
    )
    config = '{\n  "port": "not-an-integer"\n}'

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as schema_file:
        schema_file.write(schema)
        schema_path = schema_file.name

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as config_file:
        config_file.write(config)
        config_path = config_file.name

    try:
        old_argv = sys.argv
        sys.argv = ["config_validator.py", "--schema", schema_path, config_path]
        try:
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 1
        finally:
            sys.argv = old_argv
    finally:
        os.remove(schema_path)
        os.remove(config_path)


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------
def test_json_position_parser_errors() -> None:
    """Test JSONPositionParser raises ValueError for various invalid syntaxes."""
    # Empty input
    with pytest.raises(ValueError, match="Empty input"):
        JSONPositionParser("").parse()

    # Unexpected character at top level
    with pytest.raises(ValueError, match="Unexpected character"):
        JSONPositionParser("{}{}").parse()

    # Unterminated string
    with pytest.raises(ValueError, match="Unterminated string"):
        JSONPositionParser('"hello').parse()

    # Unterminated escape sequence
    with pytest.raises(ValueError, match="Unterminated escape sequence"):
        JSONPositionParser('"hello\\').parse()

    # Invalid unicode escape
    with pytest.raises(ValueError, match="Invalid unicode escape"):
        JSONPositionParser('"\\u12"').parse()

    # Invalid number format
    with pytest.raises(ValueError, match="Invalid number format"):
        JSONPositionParser("-abc").parse()

    # Unterminated array
    with pytest.raises(ValueError, match="Unterminated array"):
        JSONPositionParser("[1, 2").parse()

    # Invalid array separator
    with pytest.raises(ValueError, match="Expected ',' or ']'"):
        JSONPositionParser("[1 2]").parse()

    # Expected string key in object
    with pytest.raises(ValueError, match="Expected string key"):
        JSONPositionParser("{1: 2}").parse()

    # Expected ':' after key
    with pytest.raises(ValueError, match="Expected ':'"):
        JSONPositionParser('{"a" 2}').parse()

    # Unterminated object
    with pytest.raises(ValueError, match="Unterminated object"):
        JSONPositionParser('{"a": 2').parse()


def test_parse_yaml_with_positions_edge_cases() -> None:
    """Test parse_yaml_with_positions under different node scenarios."""
    # Empty node
    data, positions = parse_yaml_with_positions("")
    assert data is None
    assert positions == {}


class DummyError:
    def __init__(self, absolute_path: list, validator: str, message: str) -> None:
        self.absolute_path = absolute_path
        self.validator = validator
        self.message = message


def test_locate_error_position_fallbacks() -> None:
    """Test locate_error_position points to parent or default when path is not

    in position map.
    """
    positions = {
        (): (1, 1),
        ("port", "key"): (3, 5),
    }

    # 1. Required missing field mapping
    err = DummyError([], "required", "'port' is a required property")
    assert locate_error_position(err, positions) == (3, 5)

    # 2. Key matching fallback
    err2 = DummyError(["port"], "type", "invalid")
    assert locate_error_position(err2, positions) == (3, 5)

    # 3. Parent path fallback
    positions_parent = {
        ("server",): (2, 4),
    }
    err3 = DummyError(["server", "host"], "type", "invalid")
    assert locate_error_position(err3, positions_parent) == (2, 4)

    # 4. Default to top of file
    err4 = DummyError(["nonexistent"], "type", "invalid")
    assert locate_error_position(err4, {}) == (1, 1)


def test_format_error_with_context_bounds() -> None:
    """Test format_error_with_context handles color formatting and out

    of bounds lines.
    """
    content = "line1\nline2\nline3"

    # Target line exceeds total lines
    formatted = format_error_with_context(
        "test.json", content, 10, 1, "test err", "type", no_color=True
    )
    assert "Validation Error [type]" in formatted

    # Color output enabled
    formatted_color = format_error_with_context(
        "test.json", content, 2, 2, "test err", "type", no_color=False
    )
    assert "\033[91m" in formatted_color


def test_parse_and_track_fallback() -> None:
    """Test parse_and_track falls back on generic or unrecognized extensions."""
    data_json, _ = parse_and_track("config.txt", '{"port": 80}')
    assert data_json == {"port": 80}

    data_yaml, _ = parse_and_track("config.txt", "port: 80\n")
    assert data_yaml == {"port": 80}


def test_load_schema_failure() -> None:
    """Test load_schema raises RuntimeError on invalid JSON/YAML."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp.write("invalid content {")
        tmp_name = tmp.name

    try:
        with pytest.raises(RuntimeError):
            load_schema(tmp_name)
    finally:
        os.remove(tmp_name)


def test_main_cli_argument_errors(tmp_path: Path) -> None:
    """Test main function CLI validation errors (missing files or bad schemas)."""
    # 1. Schema file not found
    with pytest.raises(SystemExit) as exc:
        main(["-s", "nonexistent_schema.json", "config.json"])
    assert exc.value.code == 2

    # 2. Config file not found
    schema = tmp_path / "schema.json"
    schema.write_text('{"type": "object"}')
    with pytest.raises(SystemExit) as exc:
        main(["-s", str(schema), "nonexistent_config.json"])
    assert exc.value.code == 2

    # 3. Invalid schema exits 2
    bad_schema = tmp_path / "bad_schema.json"
    bad_schema.write_text('{"type": "invalid_type"}')
    config = tmp_path / "config.json"
    config.write_text("{}")
    with pytest.raises(SystemExit) as exc:
        main(["-s", str(bad_schema), str(config)])
    assert exc.value.code == 2

"""Unit tests for the JSON/YAML Config Validator script."""

import json
import os
import sys
import tempfile
from typing import Generator
import pytest

# Add parent directory to sys.path to enable import of config_validator
# config-validator is a kebab-case directory, so we import config_validator directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config_validator import (
    JSONPositionParser,
    parse_yaml_with_positions,
    validate_config,
    locate_error_position,
    format_error_with_context,
)


def test_json_position_parser_valid() -> None:
    """Tests that the JSON position parser works for valid JSON files."""
    json_data = '{\n  "name": "myapp",\n  "port": 8080,\n  "enabled": true,\n  "hosts": [\n    "localhost",\n    "127.0.0.1"\n  ]\n}'
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
    yaml_data = "name: myapp\nport: 8080\nfeatures:\n  - oauth\n  - saml\nsettings:\n  debug: true\n"
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

    schema = '{\n  "type": "object",\n  "properties": {\n    "port": {"type": "integer"}\n  }\n}'
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

    schema = '{\n  "type": "object",\n  "properties": {\n    "port": {"type": "integer"}\n  }\n}'
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


"""Unit tests for the api-contract-diff script."""

import json
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "checkers/api-contract-diff")

# pylint: disable=wrong-import-position
from api_contract_diff import compare_specs, load_spec, main, resolve_ref  # noqa: E402


def test_resolve_ref() -> None:
    """Test resolve_ref resolves local JSON references."""
    spec = {"components": {"schemas": {"User": {"type": "object"}}}}
    assert resolve_ref(spec, "#/components/schemas/User") == {"type": "object"}
    assert resolve_ref(spec, "#/components/schemas/Missing") == {}
    assert resolve_ref(spec, "external.yaml") == {}


def test_load_spec_json() -> None:
    """Test loading valid JSON spec."""
    spec_data = {"openapi": "3.0.0", "paths": {}}
    m_open = mock_open(read_data=json.dumps(spec_data))
    with patch("builtins.open", m_open), patch("os.path.exists", return_value=True):
        assert load_spec("spec.json") == spec_data


def test_load_spec_yaml() -> None:
    """Test loading valid YAML spec."""
    spec_data = {"openapi": "3.0.0", "paths": {}}
    import yaml

    m_open = mock_open(read_data=yaml.dump(spec_data))
    with patch("builtins.open", m_open), patch("os.path.exists", return_value=True):
        assert load_spec("spec.yaml") == spec_data


def test_compare_specs_breaking_changes() -> None:
    """Test comparing specs with various breaking changes."""
    old_spec = {
        "paths": {
            "/users": {
                "get": {
                    "parameters": [
                        {
                            "name": "id",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                        },
                        {
                            "name": "role",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "enum": ["admin", "user"]},
                        },
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "age": {"type": "integer"},
                                        },
                                        "required": ["name"],
                                    }
                                }
                            }
                        }
                    },
                },
                "post": {},
            }
        }
    }

    # Breaking changes:
    # 1. Removed path '/users'? No, keeping it, but removing 'post' method.
    # 2. Parameter 'id' query changed from optional to required.
    # 3. Parameter 'role' query removed 'user' from enum value.
    # 4. Removed response field 'name'.
    # 5. Added new required parameter 'token' query.
    new_spec = {
        "paths": {
            "/users": {
                "get": {
                    "parameters": [
                        {
                            "name": "id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "integer"},
                        },
                        {
                            "name": "role",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "enum": ["admin"]},
                        },
                        {"name": "token", "in": "query", "required": True},
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"age": {"type": "integer"}},
                                    }
                                }
                            }
                        }
                    },
                }
            }
        }
    }

    changes = compare_specs(old_spec, new_spec)
    assert any("Removed method: POST on /users" in c for c in changes)
    assert any(
        "parameter 'id' in query changed from optional to required" in c.lower()
        for c in changes
    )
    assert any(
        "removed values ['user'] from request enum" in c.lower() for c in changes
    )
    assert any(
        "added new required parameter 'token' in query" in c.lower() for c in changes
    )
    assert any("removed response field 'name'" in c.lower() for c in changes)


def test_compare_specs_removed_endpoints() -> None:
    """Test comparing specs when endpoints are completely removed."""
    old_spec = {"paths": {"/users": {"get": {}}, "/posts": {"get": {}}}}
    new_spec = {"paths": {"/users": {"get": {}}}}
    changes = compare_specs(old_spec, new_spec)
    assert changes == ["Removed endpoint: /posts"]


@patch("api_contract_diff.load_spec")
def test_main_clean_run(mock_load: MagicMock) -> None:
    """Test main command-line entry when there are no breaking changes."""
    mock_load.return_value = {"paths": {}}
    with patch("sys.argv", ["api-contract-diff", "old.json", "new.json"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0


@patch("api_contract_diff.load_spec")
def test_main_breaking_changes_text(mock_load: MagicMock) -> None:
    """Test main command-line entry when breaking changes exist (text format)."""
    mock_load.side_effect = [
        {"paths": {"/users": {"get": {}}}},
        {"paths": {}},
    ]
    with patch("sys.argv", ["api-contract-diff", "old.json", "new.json"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1


@patch("api_contract_diff.load_spec")
def test_main_breaking_changes_markdown(mock_load: MagicMock) -> None:
    """Test main command-line entry when breaking changes exist (markdown format)."""
    mock_load.side_effect = [
        {"paths": {"/users": {"get": {}}}},
        {"paths": {}},
    ]
    with patch(
        "sys.argv",
        ["api-contract-diff", "old.json", "new.json", "--format", "markdown"],
    ):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

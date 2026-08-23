import gettext
import json
import sys
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

# Add the script's directory to the python path to load the module correctly
script_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(script_dir))

import schema_drift  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_gettext_catalog():
    """Stub gettext catalog loading so argparse never opens files via mocked open()."""
    with patch(
        "gettext.translation", lambda *args, **kwargs: gettext.NullTranslations()
    ):
        yield


def test_build_schema_primitives():
    # None
    assert schema_drift.build_schema(None) == {"": {"type": "null", "nullable": True}}
    # Int
    assert schema_drift.build_schema(42) == {"": {"type": "int", "nullable": False}}
    # String
    assert schema_drift.build_schema("hello") == {
        "": {"type": "str", "nullable": False}
    }
    # Float
    assert schema_drift.build_schema(3.14) == {"": {"type": "float", "nullable": False}}
    # Boolean
    assert schema_drift.build_schema(True) == {"": {"type": "bool", "nullable": False}}


def test_build_schema_objects():
    # Simple dict
    data = {"a": 1, "b": "test"}
    expected = {
        "/": {"type": "object", "nullable": False},
        "/a": {"type": "int", "nullable": False},
        "/b": {"type": "str", "nullable": False},
    }
    assert schema_drift.build_schema(data) == expected

    # Nested dict
    data_nested = {"a": {"b": 123}}
    expected_nested = {
        "/": {"type": "object", "nullable": False},
        "/a": {"type": "object", "nullable": False},
        "/a/b": {"type": "int", "nullable": False},
    }
    assert schema_drift.build_schema(data_nested) == expected_nested


def test_build_schema_lists():
    # List of same type
    data = {"list": [1, 2, 3]}
    expected = {
        "/": {"type": "object", "nullable": False},
        "/list": {"type": "int", "nullable": False},
    }
    assert schema_drift.build_schema(data) == expected

    # List of mixed types
    data_mixed = {"list": [1, "two"]}
    expected_mixed = {
        "/": {"type": "object", "nullable": False},
        "/list": {"type": "mixed", "nullable": False},
    }
    assert schema_drift.build_schema(data_mixed) == expected_mixed

    # List of dictionaries
    data_dicts = {"list": [{"a": 1}, {"b": "two"}]}
    expected_dicts = {
        "/": {"type": "object", "nullable": False},
        "/list": {"type": "object", "nullable": False},
        "/list/a": {"type": "int", "nullable": False},
        "/list/b": {"type": "str", "nullable": False},
    }
    assert schema_drift.build_schema(data_dicts) == expected_dicts


def test_build_schema_nullable():
    data = {"a": None}
    expected = {
        "/": {"type": "object", "nullable": False},
        "/a": {"type": "null", "nullable": True},
    }
    assert schema_drift.build_schema(data) == expected


@patch("schema_drift.os.path.exists")
def test_main_files_not_found(mock_exists):
    mock_exists.return_value = False

    with patch("sys.argv", ["schema_drift.py", "a.json", "b.json"]):
        with pytest.raises(SystemExit) as exc_info:
            schema_drift.main()
    assert exc_info.value.code == 1


@patch("schema_drift.os.path.exists")
def test_main_json_parse_error(mock_exists):
    mock_exists.return_value = True

    m_open = mock_open(read_data="invalid json")
    with patch("sys.argv", ["schema_drift.py", "a.json", "b.json"]):
        with patch("builtins.open", m_open):
            with pytest.raises(SystemExit) as exc_info:
                schema_drift.main()
    assert exc_info.value.code == 1


@patch("schema_drift.os.path.exists")
def test_main_no_drifts(mock_exists):
    mock_exists.return_value = True

    data_a = json.dumps({"a": 1, "b": "hello"})
    data_b = json.dumps({"a": 2, "b": "world"})

    m_open = mock_open()
    m_open.side_effect = [
        mock_open(read_data=data_a).return_value,
        mock_open(read_data=data_b).return_value,
    ]

    with patch("sys.argv", ["schema_drift.py", "a.json", "b.json"]):
        with patch("builtins.open", m_open):
            with pytest.raises(SystemExit) as exc_info:
                schema_drift.main()
    assert exc_info.value.code == 0


@patch("schema_drift.os.path.exists")
def test_main_with_drifts(mock_exists):
    mock_exists.return_value = True

    data_a = json.dumps({"a": 1, "b": "string", "c": None, "d": True})

    data_b = json.dumps({"b": 123, "c": 456, "d": True, "e": "added"})

    m_open = mock_open()
    m_open.side_effect = [
        mock_open(read_data=data_a).return_value,
        mock_open(read_data=data_b).return_value,
    ]

    with patch("sys.argv", ["schema_drift.py", "a.json", "b.json"]):
        with patch("builtins.open", m_open):
            schema_drift.main()

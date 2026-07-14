"""Unit tests for config_migration.py."""

import json

# Add import injection to resolve checkers package
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import config_migration  # noqa: E402


def test_nested_value_helpers() -> None:
    """Test get, set, and delete nested dictionary values."""
    data = {
        "database": {
            "host": "localhost",
            "port": 5432,
        },
        "debug": True,
    }

    # Getters
    assert config_migration.get_nested_value(data, "database.host") == "localhost"
    assert config_migration.get_nested_value(data, "database.port") == 5432
    assert config_migration.get_nested_value(data, "debug") is True
    assert config_migration.get_nested_value(data, "database.nonexistent") is None
    assert config_migration.get_nested_value(data, "nonexistent.subkey") is None

    # Setters
    config_migration.set_nested_value(data, "database.port", 5433)
    assert data["database"]["port"] == 5433

    config_migration.set_nested_value(data, "new_section.subkey", "hello")
    assert data["new_section"]["subkey"] == "hello"

    # Deleters
    assert config_migration.delete_nested_value(data, "database.host") is True
    assert "host" not in data["database"]
    assert config_migration.delete_nested_value(data, "database.nonexistent") is False


def test_apply_transform() -> None:
    """Test value transformations."""
    assert config_migration.apply_transform(None, "int") is None
    assert config_migration.apply_transform("123", "int") == 123
    assert config_migration.apply_transform(123, "str") == "123"
    assert config_migration.apply_transform("123.45", "float") == 123.45
    assert config_migration.apply_transform("true", "bool") is True
    assert config_migration.apply_transform("false", "bool") is False
    assert config_migration.apply_transform("HELLO", "lower") == "hello"
    assert config_migration.apply_transform("hello", "upper") == "HELLO"
    assert config_migration.apply_transform("a, b, c", "split", ",") == ["a", "b", "c"]
    assert config_migration.apply_transform(["a", "b", "c"], "join", "-") == "a-b-c"


def test_run_declarative_rules() -> None:
    """Test executing a list of mapping rules."""
    config = {
        "old_name": "value1",
        "database_host": "localhost",
        "port": "5432",
        "obsolete": "junk",
    }
    rules = [
        {"action": "rename", "key": "old_name", "new_key": "new_name"},
        {"action": "move", "key": "database_host", "new_path": "db.host"},
        {"action": "transform", "key": "port", "type": "int"},
        {"action": "set_default", "key": "debug", "value": False},
        {"action": "delete", "key": "obsolete"},
    ]

    res = config_migration.run_declarative_rules(config, rules)
    assert res.get("new_name") == "value1"
    assert "old_name" not in res
    assert res["db"]["host"] == "localhost"
    assert res.get("port") == 5432
    assert res.get("debug") is False
    assert "obsolete" not in res


def test_find_migration_path() -> None:
    """Test routing path resolution for version jumps."""
    migrations = [
        {
            "from_version": "1.0",
            "to_version": "1.1",
            "rules": [{"action": "delete", "key": "v1"}],
        },
        {
            "from_version": "1.1",
            "to_version": "2.0",
            "rules": [{"action": "delete", "key": "v2"}],
        },
        {"from_version": "2.0", "to_version": "3.0", "rules": []},
    ]

    path = config_migration.find_migration_path(migrations, "1.0", "2.0")
    assert len(path) == 2
    assert path[0]["from_version"] == "1.0"
    assert path[1]["to_version"] == "2.0"

    with pytest.raises(ValueError):
        config_migration.find_migration_path(migrations, "1.0", "4.0")


def test_validate_schema(tmp_path: Path) -> None:
    """Test JSON Schema validations."""
    schema = {
        "type": "object",
        "properties": {
            "version": {"type": "string"},
            "port": {"type": "integer"},
        },
        "required": ["version", "port"],
    }
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(schema))

    # Valid config
    valid_data = {"version": "1.0", "port": 80}
    assert len(config_migration.validate_schema(valid_data, schema_file)) == 0

    # Invalid config
    invalid_data = {"version": "1.0", "port": "not-an-int"}
    errors = config_migration.validate_schema(invalid_data, schema_file)
    assert len(errors) > 0
    assert any("ValidationError" in err or "Validation Error" in err for err in errors)


def test_load_save_config(tmp_path: Path) -> None:
    """Test loading and saving configurations (JSON/YAML)."""
    # 1. JSON
    json_file = tmp_path / "config.json"
    data = {"version": "1.0", "debug": True}
    config_migration.save_config(json_file, data)
    assert json_file.exists()
    loaded = config_migration.load_config(json_file)
    assert loaded == data

    # 2. YAML (if package is available)
    if config_migration.HAS_YAML:
        yaml_file = tmp_path / "config.yaml"
        config_migration.save_config(yaml_file, data)
        assert yaml_file.exists()
        loaded_yaml = config_migration.load_config(yaml_file)
        assert loaded_yaml == data


def test_load_custom_migration_script(tmp_path: Path) -> None:
    """Test dynamic loading of python custom script scripts."""
    script_content = """
def custom_migrate(config):
    config["custom_field"] = "added_by_script"
    return config
"""
    script_file = tmp_path / "migrate.py"
    script_file.write_text(script_content)

    fn = config_migration.load_custom_migration_script(script_file)
    res = fn({"version": "1.0"})
    assert res.get("custom_field") == "added_by_script"


@patch("sys.exit")
def test_main_cli_custom_script(mock_exit: MagicMock, tmp_path: Path) -> None:
    """Test main function CLI execution path using custom scripts."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"version": "1.0"}))

    script_content = """
def custom_migrate(config):
    config["version"] = "2.0"
    config["custom_field"] = "value"
    return config
"""
    script_file = tmp_path / "migrate.py"
    script_file.write_text(script_content)
    report_file = tmp_path / "report.json"

    args = [
        "config_migration.py",
        "-i",
        str(config_file),
        "-c",
        str(script_file),
        "--report",
        str(report_file),
    ]

    with patch("sys.argv", args):
        config_migration.main()
        # Verify changes saved and report written
        migrated = json.loads(config_file.read_text(encoding="utf-8"))
        assert migrated.get("version") == "2.0"
        assert migrated.get("custom_field") == "value"

        assert report_file.exists()
        report = json.loads(report_file.read_text(encoding="utf-8"))
        assert report.get("status") == "success"


@patch("sys.exit")
def test_main_cli_rules(mock_exit: MagicMock, tmp_path: Path) -> None:
    """Test main function CLI execution path using declarative rules file."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"version": "1.0", "old_key": "old_val"}))

    rules_data = {
        "migrations": [
            {
                "from_version": "1.0",
                "to_version": "2.0",
                "rules": [
                    {"action": "rename", "key": "old_key", "new_key": "new_key"},
                ],
            }
        ]
    }
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps(rules_data))

    args = [
        "config_migration.py",
        "-i",
        str(config_file),
        "-r",
        str(rules_file),
        "-t",
        "2.0",
    ]

    with patch("sys.argv", args):
        config_migration.main()
        migrated = json.loads(config_file.read_text(encoding="utf-8"))
        assert migrated.get("version") == "2.0"
        assert migrated.get("new_key") == "old_val"
        assert "old_key" not in migrated


def test_load_save_errors(tmp_path: Path) -> None:
    """Test exceptions on unsupported file types and invalid formats."""
    # Unsupported load format
    txt_file = tmp_path / "config.txt"
    txt_file.write_text("some content")
    with pytest.raises(ValueError, match="Unsupported configuration file format"):
        config_migration.load_config(txt_file)

    # JSON not dictionary
    bad_json = tmp_path / "config.json"
    bad_json.write_text("[]")
    with pytest.raises(ValueError, match="JSON configuration must be a dictionary"):
        config_migration.load_config(bad_json)

    # YAML not dictionary
    if config_migration.HAS_YAML:
        bad_yaml = tmp_path / "config.yaml"
        bad_yaml.write_text("- item1\n- item2")
        with pytest.raises(ValueError, match="YAML configuration must be a dictionary"):
            config_migration.load_config(bad_yaml)

    # Save unsupported format
    with pytest.raises(ValueError, match="Unsupported configuration file format"):
        config_migration.save_config(txt_file, {})

    # TOML save unsupported
    toml_file = tmp_path / "config.toml"
    with pytest.raises(ValueError, match="Writing TOML is not natively supported"):
        config_migration.save_config(toml_file, {})


def test_main_cli_errors(tmp_path: Path) -> None:
    """Test CLI error pathways and non-zero exit codes."""
    # 1. Input path doesn't exist
    args1 = ["config_migration.py", "-i", "nonexistent.json", "-t", "2.0"]
    with patch("sys.argv", args1):
        with pytest.raises(SystemExit) as exc:
            config_migration.main()
        assert exc.value.code == 1

    # 2. Neither rules nor script
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"version": "1.0"}))
    args2 = ["config_migration.py", "-i", str(config_file), "-t", "2.0"]
    with patch("sys.argv", args2):
        with pytest.raises(SystemExit) as exc:
            config_migration.main()
        assert exc.value.code == 1

    # 3. Rules specified without target version
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps({"migrations": []}))
    args3 = ["config_migration.py", "-i", str(config_file), "-r", str(rules_file)]
    with patch("sys.argv", args3):
        with pytest.raises(SystemExit) as exc:
            config_migration.main()
        assert exc.value.code == 1

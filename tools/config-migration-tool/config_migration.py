#!/usr/bin/env python3
"""Config Migration Tool.

Converts old configuration file schemas to new versions, creating automatic
backups and generating migration reports.
"""

import argparse
import datetime
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Optional

# Try importing yaml, jsonschema, and tomllib
try:
    import yaml  # type: ignore[import-untyped]

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import jsonschema

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

try:
    import tomllib  # type: ignore[import-not-found, unused-ignore]

    HAS_TOMLLIB = True
except ImportError:
    HAS_TOMLLIB = False


def load_config(file_path: Path) -> dict[str, Any]:
    """Load configuration from JSON or YAML file.

    Args:
        file_path: Path to the configuration file.

    Returns:
        The configuration dictionary.
    """
    ext = file_path.suffix.lower()
    if ext == ".json":
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("JSON configuration must be a dictionary.")
            return data
    elif ext in (".yaml", ".yml"):
        if not HAS_YAML:
            raise ImportError(
                "PyYAML package is required to read YAML configuration files."
            )
        with file_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError("YAML configuration must be a dictionary.")
            return data
    elif ext == ".toml":
        if not HAS_TOMLLIB:
            raise ImportError("Python 3.11+ tomllib is required to read TOML files.")
        with file_path.open("rb") as f:
            return tomllib.load(f)
    else:
        raise ValueError(f"Unsupported configuration file format: {file_path.suffix}")


def save_config(file_path: Path, data: dict[str, Any]) -> None:
    """Save configuration to JSON or YAML file.

    Args:
        file_path: Path to save the file.
        data: Configuration dictionary to save.
    """
    ext = file_path.suffix.lower()
    if ext == ".json":
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    elif ext in (".yaml", ".yml"):
        if not HAS_YAML:
            raise ImportError("PyYAML package is required to write YAML files.")
        with file_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False)
    elif ext == ".toml":
        # We don't have a stdlib TOML writer, format as a simple key-value string
        # or JSON-like structure. For safety, recommend JSON or YAML.
        raise ValueError("Writing TOML is not natively supported.")
    else:
        raise ValueError(f"Unsupported configuration file format: {file_path.suffix}")


def get_nested_value(d: dict[str, Any], path: str) -> Any:
    """Retrieve a value from a nested dictionary path (dot notation).

    Args:
        d: The dictionary.
        path: The dot-separated path (e.g., 'database.host').

    Returns:
        The value or None if not found.
    """
    parts = path.split(".")
    curr: Any = d
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            return None
    return curr


def set_nested_value(d: dict[str, Any], path: str, value: Any) -> None:
    """Set a value in a nested dictionary path (dot notation).

    Args:
        d: The dictionary.
        path: The dot-separated path (e.g., 'database.host').
        value: The value to set.
    """
    parts = path.split(".")
    curr = d
    for part in parts[:-1]:
        if part not in curr or not isinstance(curr[part], dict):
            curr[part] = {}
        curr = curr[part]
    curr[parts[-1]] = value


def delete_nested_value(d: dict[str, Any], path: str) -> bool:
    """Delete a key from a nested dictionary path (dot notation).

    Args:
        d: The dictionary.
        path: The dot-separated path.

    Returns:
        True if deleted, False otherwise.
    """
    parts = path.split(".")
    curr = d
    for part in parts[:-1]:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            return False
    if isinstance(curr, dict) and parts[-1] in curr:
        del curr[parts[-1]]
        return True
    return False


def apply_transform(val: Any, transform_type: str, delimiter: str = ",") -> Any:
    # pylint: disable=too-many-return-statements, no-else-return
    """Apply a type or string transformation on a value.

    Args:
        val: The value to transform.
        transform_type: Type of transformation ('int', 'str', 'bool', etc.).
        delimiter: Separator for split/join operations.

    Returns:
        The transformed value.
    """
    if val is None:
        return None

    if transform_type == "int":
        return int(val)
    elif transform_type == "str":
        return str(val)
    elif transform_type == "float":
        return float(val)
    elif transform_type == "bool":
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes", "on")
        return bool(val)
    elif transform_type == "lower" and isinstance(val, str):
        return val.lower()
    elif transform_type == "upper" and isinstance(val, str):
        return val.upper()
    elif transform_type == "split" and isinstance(val, str):
        return [item.strip() for item in val.split(delimiter)]
    elif transform_type == "join" and isinstance(val, list):
        return delimiter.join(str(item) for item in val)

    return val


def run_declarative_rules(
    config: dict[str, Any], rules: list[dict[str, Any]]
) -> dict[str, Any]:
    # pylint: disable=too-many-branches
    """Apply a list of declarative rules to a configuration dictionary.

    Args:
        config: The configuration to mutate.
        rules: The rules mapping.

    Returns:
        The mutated configuration dictionary.
    """
    for rule in rules:
        action = rule.get("action")
        key = rule.get("key")

        if not action or not key:
            continue

        if action == "rename":
            new_key = rule.get("new_key")
            if new_key and key in config:
                config[new_key] = config.pop(key)

        elif action == "move":
            new_path = rule.get("new_path")
            if new_path:
                val = get_nested_value(config, key)
                if val is not None:
                    set_nested_value(config, new_path, val)
                    delete_nested_value(config, key)

        elif action == "transform":
            t_type = rule.get("type")
            delim = rule.get("delimiter", ",")
            if t_type:
                val = get_nested_value(config, key)
                if val is not None:
                    new_val = apply_transform(val, t_type, delim)
                    set_nested_value(config, key, new_val)

        elif action == "set_default":
            default_val = rule.get("value")
            if get_nested_value(config, key) is None:
                set_nested_value(config, key, default_val)

        elif action == "delete":
            delete_nested_value(config, key)

    return config


def load_custom_migration_script(
    script_path: Path,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Dynamically load a custom Python migration function from a script.

    Args:
        script_path: Path to the Python script.

    Returns:
        A callable function that executes custom migration logic.
    """
    spec = importlib.util.spec_from_file_location("custom_migration", script_path)
    if not spec or not spec.loader:
        raise ImportError(f"Could not load custom script specification: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "custom_migrate"):
        raise AttributeError(
            f"Custom migration script {script_path} "
            "must define a 'custom_migrate' function."
        )
    return module.custom_migrate  # type: ignore[no-any-return]


def validate_schema(data: dict[str, Any], schema_path: Path) -> list[str]:
    # pylint: disable=broad-exception-caught
    """Validate configuration data against a JSON Schema.

    Args:
        data: The configuration dictionary.
        schema_path: Path to the JSON Schema.

    Returns:
        A list of validation error strings.
    """
    if not HAS_JSONSCHEMA:
        return ["Warning: jsonschema is not installed. Skipping schema validation."]

    try:
        with schema_path.open("r", encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(instance=data, schema=schema)
        return []
    except jsonschema.exceptions.ValidationError as err:
        return [f"Validation Error: {err.message} at path '{list(err.absolute_path)}'"]
    except Exception as err:
        return [f"Schema Loading Error: {err}"]


def find_migration_path(
    migrations: list[dict[str, Any]], current_ver: str, target_ver: str
) -> list[dict[str, Any]]:
    """Determine the sequential list of rules/scripts to migrate across versions.

    Args:
        migrations: List of all migration specifications.
        current_ver: Starting version.
        target_ver: End target version.

    Returns:
        A list of migration step dictionaries.
    """
    # Simple BFS/DFS traversal to find a path in the version migration DAG
    adj: dict[str, list[dict[str, Any]]] = {}
    for mig in migrations:
        frm = mig.get("from_version")
        to = mig.get("to_version")
        if frm and to:
            if frm not in adj:
                adj[frm] = []
            adj[frm].append(mig)

    # Queue of path steps: (current_node, [migration_dicts])
    queue: list[tuple[str, list[dict[str, Any]]]] = [(current_ver, [])]
    visited: set[str] = {current_ver}

    while queue:
        node, path = queue.pop(0)
        if node == target_ver:
            return path

        for edge in adj.get(node, []):
            nxt = edge["to_version"]
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, path + [edge]))

    raise ValueError(
        f"No migration path found from version '{current_ver}' "
        f"to target version '{target_ver}'."
    )


def create_backup(config_path: Path) -> Path:
    """Create a backup of the configuration file.

    Args:
        config_path: Path to the config file.

    Returns:
        Path to the created backup.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.parent / f"{config_path.name}.bak_{timestamp}"
    shutil.copy2(config_path, backup_path)
    return backup_path


def main() -> None:
    # pylint: disable=too-many-locals, too-many-branches
    # pylint: disable=too-many-statements, broad-exception-caught
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert configuration schemas with backups " "and migration reports."
        )
    )
    parser.add_argument(
        "-i", "--input", required=True, help="Path to the config file to migrate."
    )
    parser.add_argument(
        "-r",
        "--rules",
        help="Path to the rules file (JSON or YAML) containing migrations.",
    )
    parser.add_argument(
        "-c", "--custom-script", help="Path to custom Python migration script."
    )
    parser.add_argument(
        "-t",
        "--target-version",
        help="Target version to migrate to (required if using rules file).",
    )
    parser.add_argument(
        "-s", "--schema", help="Path to JSON Schema to validate the output config."
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to write the migrated config (defaults to input path).",
    )
    parser.add_argument(
        "--version-key",
        default="version",
        help=(
            "Key name containing schema version in configuration "
            "(default: 'version')."
        ),
    )
    parser.add_argument(
        "--report",
        help="Path to save the migration report (JSON).",
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Disable configuration file backup."
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input config file does not exist: {args.input}")
        sys.exit(1)

    # 1. Load config
    try:
        config_data = load_config(input_path)
    except Exception as err:
        print(f"Error loading configuration: {err}")
        sys.exit(1)

    backup_file: Optional[Path] = None
    if not args.no_backup:
        try:
            backup_file = create_backup(input_path)
            print(f"Backup created at: {backup_file}")
        except Exception as err:
            print(f"Error creating backup file: {err}")
            sys.exit(1)

    original_version = config_data.get(args.version_key, "unknown")
    target_version = args.target_version if args.target_version else "custom"

    applied_steps: list[str] = []
    report_errors: list[str] = []

    # 2. Run migration logic
    if args.custom_script:
        custom_path = Path(args.custom_script)
        if not custom_path.exists():
            print(f"Error: Custom script does not exist: {args.custom_script}")
            sys.exit(1)
        try:
            print(f"Applying custom script migration: {args.custom_script}")
            custom_fn = load_custom_migration_script(custom_path)
            config_data = custom_fn(config_data)
            applied_steps.append(f"Custom Script: {args.custom_script}")
        except Exception as err:
            print(f"Error running custom migration: {err}")
            sys.exit(1)

    elif args.rules:
        rules_path = Path(args.rules)
        if not rules_path.exists():
            print(f"Error: Rules file does not exist: {args.rules}")
            sys.exit(1)

        try:
            rules_data = load_config(rules_path)
            migrations_list = rules_data.get("migrations", [])
            if not migrations_list and isinstance(rules_data, dict):
                # Fallback if rules file contains a single migration node
                migrations_list = [rules_data]

            if not args.target_version:
                print("Error: --target-version is required when using a rules file.")
                sys.exit(1)

            # Determine routing pathway
            pathway = find_migration_path(
                migrations_list, str(original_version), str(target_version)
            )

            for step in pathway:
                from_v = step.get("from_version")
                to_v = step.get("to_version")
                print(f"Migrating config from version {from_v} to {to_v}...")

                # Apply declarative rules
                rules = step.get("rules", [])
                config_data = run_declarative_rules(config_data, rules)

                # Set new version key
                config_data[args.version_key] = to_v
                applied_steps.append(f"{from_v} -> {to_v}")

        except Exception as err:
            print(f"Migration failed: {err}")
            sys.exit(1)
    else:
        print("Error: Either --rules (-r) or --custom-script (-c) must be specified.")
        sys.exit(1)

    # 3. Schema validation
    if args.schema:
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"Error: Schema file does not exist: {args.schema}")
            sys.exit(1)
        print(f"Validating migrated config against schema: {args.schema}")
        errors = validate_schema(config_data, schema_path)
        if errors:
            print("\nSchema validation warnings/errors:")
            for err_msg in errors:
                print(f"  - {err_msg}")
            report_errors.extend(errors)
        else:
            print("Configuration schema validation succeeded.")

    # 4. Save migrated config
    out_path = Path(args.output) if args.output else input_path
    try:
        save_config(out_path, config_data)
        print(f"Migrated configuration saved to: {out_path}")
    except Exception as err:
        print(f"Error saving migrated configuration: {err}")
        sys.exit(1)

    # 5. Save report
    if args.report:
        report_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "success" if not report_errors else "warnings",
            "input_file": str(input_path),
            "output_file": str(out_path),
            "backup_file": str(backup_file) if backup_file else None,
            "original_version": original_version,
            "target_version": target_version,
            "applied_steps": applied_steps,
            "errors": report_errors,
        }
        try:
            report_path = Path(args.report)
            with report_path.open("w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2)
            print(f"Migration report written to: {report_path}")
        except Exception as err:
            print(f"Error writing migration report: {err}")


if __name__ == "__main__":
    main()

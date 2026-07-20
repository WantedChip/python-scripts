import os
import sys
from io import StringIO
from unittest.mock import patch

# Add parent directory to sys.path to import config_map
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config_map  # noqa: E402


def test_scan_cli_arguments(tmp_path):
    file_content = (
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--port', '-p', default=8080, help='port')\n"
        "parser.add_argument('--host', default='localhost')\n"
        "parser.add_argument('positional')\n"
    )
    dummy_dir = tmp_path / "src"
    dummy_dir.mkdir()
    dummy_file = dummy_dir / "app.py"
    dummy_file.write_text(file_content)

    results = config_map.scan_cli_arguments(str(tmp_path))

    assert len(results) == 2
    port_arg = next(r for r in results if "port" in r["flag"])
    assert port_arg["flag"] == "--port / -p"
    assert port_arg["name"] == "port"
    assert port_arg["default"] == "8080"

    host_arg = next(r for r in results if "host" in r["flag"])
    assert host_arg["flag"] == "--host"
    assert host_arg["name"] == "host"
    assert host_arg["default"] == "localhost"


def test_scan_env_variables(tmp_path):
    file_content = (
        "import os\n"
        "port = os.getenv('PORT', 8080)\n"
        "host = os.environ.get(\"HOST\", 'localhost')\n"
        "key = os.environ['SECRET_KEY']\n"
    )
    dummy_dir = tmp_path / "src"
    dummy_dir.mkdir()
    dummy_file = dummy_dir / "app.py"
    dummy_file.write_text(file_content)

    results = config_map.scan_env_variables(str(tmp_path))

    assert len(results) == 3

    port_var = next(r for r in results if r["name"] == "PORT")
    assert port_var["default"] == "8080"

    host_var = next(r for r in results if r["name"] == "HOST")
    assert host_var["default"] == "localhost"

    secret_var = next(r for r in results if r["name"] == "SECRET_KEY")
    assert "Throws KeyException" in secret_var["default"]


def test_scan_file_configurations(tmp_path):
    file_content = (
        "import json, yaml, toml\n"
        "data1 = json.load(open('config.json'))\n"
        "data2 = yaml.safe_load(stream)\n"
        "data3 = toml.loads(text)\n"
    )
    dummy_dir = tmp_path / "src"
    dummy_dir.mkdir()
    dummy_file = dummy_dir / "app.py"
    dummy_file.write_text(file_content)

    results = config_map.scan_file_configurations(str(tmp_path))

    assert len(results) == 3
    loaders = [r["loader"] for r in results]
    assert any("json.load" in ldr for ldr in loaders)
    assert any("yaml.safe_load" in ldr for ldr in loaders)
    assert any("toml.loads" in ldr for ldr in loaders)


def test_main_path_not_exists():
    with patch("os.path.exists", return_value=False), patch(
        "sys.argv", ["config_map.py", "/nonexistent"]
    ):
        try:
            config_map.main()
        except SystemExit as excinfo:
            assert excinfo.code == 1


def test_main_success(tmp_path):
    file_content = (
        "import argparse, os, json\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--test-flag', default='yep')\n"
        "key = os.getenv('TEST_ENV', 'abc')\n"
        "cfg = json.loads(text)\n"
    )
    dummy_file = tmp_path / "app.py"
    dummy_file.write_text(file_content)

    with patch("sys.argv", ["config_map.py", str(tmp_path)]):
        new_stdout = StringIO()
        with patch("sys.stdout", new_stdout):
            config_map.main()

        output = new_stdout.getvalue()
        assert "CONFIG MAP: RESOLUTION HIERARCHY" in output
        assert "CLI ARGUMENTS DETECTED" in output
        assert "--test-flag" in output
        assert "ENVIRONMENT VARIABLES DETECTED" in output
        assert "TEST_ENV" in output
        assert "SETTINGS FILE LOADERS DETECTED" in output
        assert "json.loads" in output

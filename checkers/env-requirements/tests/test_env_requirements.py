import os
import sys
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

# Add import injection to resolve env_requirements
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import env_requirements  # noqa: E402


def test_scan_source_env_vars_success():
    mock_walk = [
        ("/src", [], ["app.py", "ignored.txt"]),
    ]
    app_py_content = """
    import os
    # Bracket required access:
    val = os.environ['REQ_VAR_1']
    val2 = os.environ["REQ_VAR_2"]
    # Standard get access:
    opt = os.getenv("OPT_VAR_1")
    opt2 = os.environ.get("OPT_VAR_2")
    # Invalid access or comment
    # os.getenv("COMMENTED_VAR")
    """

    def mock_open_side_effect(filepath, *args, **kwargs):
        if filepath.replace(os.sep, "/").endswith("app.py"):
            return mock_open(read_data=app_py_content)()
        raise OSError()

    with patch("os.walk", return_value=mock_walk), patch(
        "builtins.open", side_effect=mock_open_side_effect
    ):

        found = env_requirements.scan_source_env_vars("/src")

        assert "REQ_VAR_1" in found
        assert found["REQ_VAR_1"]["required"] is True

        assert "REQ_VAR_2" in found
        assert found["REQ_VAR_2"]["required"] is True

        assert "OPT_VAR_1" in found
        assert found["OPT_VAR_1"]["required"] is False

        assert "OPT_VAR_2" in found
        assert found["OPT_VAR_2"]["required"] is False

        assert "COMMENTED_VAR" in found
        assert found["COMMENTED_VAR"]["required"] is False


def test_scan_source_env_vars_oserror():
    mock_walk = [("/src", [], ["app.py"])]
    with patch("os.walk", return_value=mock_walk), patch(
        "builtins.open", side_effect=OSError
    ):
        found = env_requirements.scan_source_env_vars("/src")
        assert found == {}


def test_scan_config_env_vars_nonexistent():
    assert env_requirements.scan_config_env_vars("nonexistent_file") == set()


def test_scan_config_env_vars_success():
    content = """
    # Comment
    PORT=8080

    DB_HOST = localhost
    # Another comment
    API_KEY=
    """
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=content)
    ):
        vars_set = env_requirements.scan_config_env_vars(".env.example")
        assert vars_set == {"PORT", "DB_HOST", "API_KEY"}


def test_scan_config_env_vars_oserror():
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", side_effect=OSError
    ):
        vars_set = env_requirements.scan_config_env_vars(".env.example")
        assert vars_set == set()


def test_scan_docker_compose_nonexistent():
    assert env_requirements.scan_docker_compose("nonexistent_compose") == set()


def test_scan_docker_compose_success():
    content_upper = """
    version: '3'
    services:
      app:
        environment:
          PORT: 8080
          DB_PASSWORD: secret
          lower_var: value
    """
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=content_upper)
    ):
        vars_set = env_requirements.scan_docker_compose("docker-compose.yml")
        assert vars_set == {"PORT", "DB_PASSWORD"}
        assert "lower_var" not in vars_set


def test_scan_docker_compose_oserror():
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", side_effect=OSError
    ):
        vars_set = env_requirements.scan_docker_compose("docker-compose.yml")
        assert vars_set == set()


@patch("sys.argv", ["env_requirements.py", "nonexistent_dir"])
@patch("os.path.exists", return_value=False)
def test_main_nonexistent_dir(mock_exists):
    with pytest.raises(SystemExit) as exc_info:
        env_requirements.main()
    assert exc_info.value.code == 1


@patch("sys.argv", ["env_requirements.py", "/src"])
@patch("os.path.exists", return_value=True)
@patch("env_requirements.scan_source_env_vars", return_value={})
@patch("env_requirements.scan_config_env_vars", return_value=set())
@patch("env_requirements.scan_docker_compose", return_value=set())
def test_main_no_vars(mock_compose, mock_config, mock_source, mock_exists):
    with patch("sys.stdout"), pytest.raises(SystemExit) as exc_info:
        env_requirements.main()
    assert exc_info.value.code == 0


@patch("sys.argv", ["env_requirements.py", "/src"])
@patch("os.path.exists", return_value=True)
@patch("env_requirements.scan_source_env_vars")
@patch("env_requirements.scan_config_env_vars")
@patch("env_requirements.scan_docker_compose")
def test_main_with_vars(mock_compose, mock_config, mock_source, mock_exists):
    mock_source.return_value = {
        "DB_PORT": {"required": True, "occurrences": [("/src/app.py", 10)]},
        "API_KEY": {"required": False, "occurrences": [("/src/app.py", 15)]},
        "DB_USER": {"required": True, "occurrences": [("/src/app.py", 20)]},
    }
    mock_config.return_value = {"DB_PORT"}
    mock_compose.return_value = {"STALE_VAR"}

    with patch("sys.stdout") as mock_stdout:
        env_requirements.main()

        # Verify printing occurs
        assert mock_stdout.write.called

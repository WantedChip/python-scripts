import os
import subprocess
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add target directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import readme_doctor  # noqa: E402


def test_extract_commands_file_not_found():
    with patch("os.path.exists", return_value=False):
        commands = readme_doctor.extract_commands("nonexistent.md")
        assert commands == []


def test_extract_commands_os_error():
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", side_effect=OSError
    ):
        commands = readme_doctor.extract_commands("README.md")
        assert commands == []


def test_extract_commands_success():
    mock_md = """
# Title
Here is some info.

```bash
# This is a comment
$ pip install -r requirements.txt
> python main.py --help
:: Ignore this command
cd /app
```

An ignoreable code block:
```python
print("python code block")
```
"""
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=mock_md)
    ):
        commands = readme_doctor.extract_commands("README.md")
        assert commands == [
            "pip install -r requirements.txt",
            "python main.py --help",
            "cd /app",
        ]


@patch("subprocess.run")
def test_create_venv_and_run_venv_creation_failed(mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, "venv")
    results = readme_doctor.create_venv_and_run(["pip install"], "/sandbox")
    assert results == []


@pytest.mark.parametrize(
    "platform,expected_pip_parts,expected_python_parts",
    [
        ("win32", ["Scripts", "pip.exe"], ["Scripts", "python.exe"]),
        ("linux", ["bin", "pip"], ["bin", "python"]),
    ],
)
@patch("sys.platform")
@patch("os.getcwd")
@patch("os.listdir")
@patch("os.path.isdir")
@patch("shutil.copy2")
@patch("shutil.copytree")
@patch("subprocess.run")
def test_create_venv_and_run_success(
    mock_run,
    mock_copytree,
    mock_copy2,
    mock_isdir,
    mock_listdir,
    mock_getcwd,
    mock_platform,
    platform,
    expected_pip_parts,
    expected_python_parts,
):
    mock_platform.__get__ = MagicMock(return_value=platform)
    with patch("sys.platform", platform):
        mock_getcwd.return_value = "/workspace"
        mock_listdir.return_value = []

        # We need mock_run to handle two calls:
        # 1. venv creation
        # 2. command execution
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "output"
        mock_res.stderr = ""
        mock_run.return_value = mock_res

        commands = [
            "pip install -r requirements.txt",
            "python main.py",
            "other-command",
        ]
        results = readme_doctor.create_venv_and_run(commands, "/sandbox")

        expected_pip = os.path.join(*expected_pip_parts)
        expected_python = os.path.join(*expected_python_parts)

        assert len(results) == 3
        assert results[0]["command"] == "pip install -r requirements.txt"
        assert expected_pip in results[0]["isolated_command"]
        assert results[1]["command"] == "python main.py"
        assert expected_python in results[1]["isolated_command"]
        assert results[2]["command"] == "other-command"
        assert results[2]["isolated_command"] == "other-command"


@patch("sys.platform", "linux")
@patch("os.getcwd")
@patch("os.listdir")
@patch("subprocess.run")
def test_create_venv_and_run_timeout(mock_run, mock_listdir, mock_getcwd):
    mock_getcwd.return_value = "/workspace"
    mock_listdir.return_value = []

    mock_run.side_effect = [
        MagicMock(returncode=0),
        subprocess.TimeoutExpired("pip install", 90.0),
    ]

    results = readme_doctor.create_venv_and_run(["pip install"], "/sandbox")
    assert len(results) == 1
    assert results[0]["exit_code"] == -1
    assert results[0]["stderr"] == "Command timed out"


@patch("sys.platform", "linux")
@patch("os.getcwd")
@patch("os.listdir")
@patch("subprocess.run")
def test_create_venv_and_run_exception(mock_run, mock_listdir, mock_getcwd):
    mock_getcwd.return_value = "/workspace"
    mock_listdir.return_value = []

    mock_run.side_effect = [
        MagicMock(returncode=0),
        OSError("Unknown error"),
    ]

    results = readme_doctor.create_venv_and_run(["pip install"], "/sandbox")
    assert len(results) == 1
    assert results[0]["exit_code"] == -2
    assert results[0]["stderr"] == "Unknown error"


@patch("sys.argv", ["readme_doctor.py", "nonexistent.md"])
def test_main_file_not_found():
    with pytest.raises(SystemExit) as excinfo:
        readme_doctor.main()
    assert excinfo.value.code == 1


@patch("sys.argv", ["readme_doctor.py", "README.md"])
@patch("os.path.exists", return_value=True)
@patch("readme_doctor.extract_commands", return_value=[])
def test_main_no_commands(mock_extract, mock_exists):
    with pytest.raises(SystemExit) as excinfo:
        readme_doctor.main()
    assert excinfo.value.code == 0


@patch("sys.argv", ["readme_doctor.py", "README.md", "-d"])
@patch("os.path.exists", return_value=True)
@patch("readme_doctor.extract_commands", return_value=["pip install"])
def test_main_dry_run(mock_extract, mock_exists):
    with pytest.raises(SystemExit) as excinfo:
        readme_doctor.main()
    assert excinfo.value.code == 0


@patch("sys.argv", ["readme_doctor.py", "README.md"])
@patch("os.path.exists", return_value=True)
@patch("readme_doctor.extract_commands", return_value=["pip install"])
@patch("readme_doctor.create_venv_and_run")
@patch("tempfile.TemporaryDirectory")
def test_main_execution_success(mock_tempdir, mock_venv_run, mock_extract, mock_exists):
    mock_tempdir.return_value.__enter__.return_value = "/sandbox"
    mock_venv_run.return_value = [
        {"command": "pip install", "exit_code": 0, "stdout": "", "stderr": ""}
    ]

    readme_doctor.main()


@patch("sys.argv", ["readme_doctor.py", "README.md"])
@patch("os.path.exists", return_value=True)
@patch("readme_doctor.extract_commands", return_value=["pip install"])
@patch("readme_doctor.create_venv_and_run")
@patch("tempfile.TemporaryDirectory")
def test_main_execution_failed(mock_tempdir, mock_venv_run, mock_extract, mock_exists):
    mock_tempdir.return_value.__enter__.return_value = "/sandbox"
    mock_venv_run.return_value = [
        {"command": "pip install", "exit_code": 1, "stdout": "", "stderr": "failed"}
    ]

    with pytest.raises(SystemExit) as excinfo:
        readme_doctor.main()
    assert excinfo.value.code == 1

import os
import subprocess
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add target directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import readme_command_tester  # noqa: E402


def test_extract_readme_commands_file_not_found():
    with patch("os.path.exists", return_value=False):
        commands = readme_command_tester.extract_readme_commands("nonexistent.md")
        assert commands == []


def test_extract_readme_commands_os_error():
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", side_effect=OSError
    ):
        commands = readme_command_tester.extract_readme_commands("README.md")
        assert commands == []


def test_extract_readme_commands_success():
    mock_md = """
# Title
Here is some info.

```bash
# This is a comment
$ echo "hello"
> python manage.py run
:: Ignore this command
cd /app
```

And some cmd block:
```powershell
dir
```

An ignoreable code block:
```python
print("python code block")
```
"""
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=mock_md)
    ):
        commands = readme_command_tester.extract_readme_commands("README.md")
        assert commands == ['echo "hello"', "python manage.py run", "cd /app", "dir"]


@patch("os.getcwd")
@patch("os.listdir")
@patch("os.path.isdir")
@patch("shutil.copy2")
@patch("shutil.copytree")
@patch("subprocess.run")
def test_run_commands_in_sandbox_success(
    mock_run, mock_copytree, mock_copy2, mock_isdir, mock_listdir, mock_getcwd
):
    mock_getcwd.return_value = "/workspace"
    mock_listdir.return_value = ["file1.txt", "dir1", ".git", "sandbox"]

    def isdir_side_effect(path):
        if "dir1" in path:
            return True
        return False

    mock_isdir.side_effect = isdir_side_effect

    mock_res1 = MagicMock()
    mock_res1.returncode = 0
    mock_res1.stdout = "hello"
    mock_res1.stderr = ""
    mock_run.return_value = mock_res1

    # Using abspath to ensure sandbox is skipped in the loop correctly
    sandbox_dir = os.path.abspath("sandbox")
    commands = ["echo hello"]
    results = readme_command_tester.run_commands_in_sandbox(commands, sandbox_dir)

    # Verify directory copy exclusions and execution using cross-platform os.path.join
    mock_copy2.assert_called_once_with(
        os.path.join("/workspace", "file1.txt"), os.path.join(sandbox_dir, "file1.txt")
    )
    mock_copytree.assert_called_once_with(
        os.path.join("/workspace", "dir1"), os.path.join(sandbox_dir, "dir1")
    )

    mock_run.assert_called_once_with(
        "echo hello",
        shell=True,
        cwd=sandbox_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60.0,
        check=False,
    )
    assert len(results) == 1
    assert results[0]["exit_code"] == 0
    assert results[0]["stdout"] == "hello"


@patch("os.getcwd")
@patch("os.listdir")
@patch("subprocess.run")
def test_run_commands_in_sandbox_failure(mock_run, mock_listdir, mock_getcwd):
    mock_getcwd.return_value = "/workspace"
    mock_listdir.return_value = []

    mock_res1 = MagicMock()
    mock_res1.returncode = 1
    mock_res1.stdout = ""
    mock_res1.stderr = "error"
    mock_run.return_value = mock_res1

    results = readme_command_tester.run_commands_in_sandbox(
        ["cmd1", "cmd2"], "/sandbox"
    )

    # Execution should stop after the first failed command
    assert len(results) == 1
    assert results[0]["exit_code"] == 1
    assert results[0]["stderr"] == "error"
    assert mock_run.call_count == 1


@patch("os.getcwd")
@patch("os.listdir")
@patch("subprocess.run")
def test_run_commands_in_sandbox_timeout(mock_run, mock_listdir, mock_getcwd):
    mock_getcwd.return_value = "/workspace"
    mock_listdir.return_value = []

    mock_run.side_effect = subprocess.TimeoutExpired("cmd1", 60.0)

    results = readme_command_tester.run_commands_in_sandbox(
        ["cmd1", "cmd2"], "/sandbox"
    )

    assert len(results) == 1
    assert results[0]["exit_code"] == -1
    assert results[0]["stderr"] == "Execution timed out"


@patch("os.getcwd")
@patch("os.listdir")
@patch("subprocess.run")
def test_run_commands_in_sandbox_exception(mock_run, mock_listdir, mock_getcwd):
    mock_getcwd.return_value = "/workspace"
    mock_listdir.return_value = []

    mock_run.side_effect = OSError("System crash")

    results = readme_command_tester.run_commands_in_sandbox(["cmd1"], "/sandbox")

    assert len(results) == 1
    assert results[0]["exit_code"] == -2
    assert results[0]["stderr"] == "System crash"


@patch("sys.argv", ["readme_command_tester.py", "nonexistent.md"])
def test_main_file_not_found():
    with pytest.raises(SystemExit) as excinfo:
        readme_command_tester.main()
    assert excinfo.value.code == 1


@patch("sys.argv", ["readme_command_tester.py", "README.md"])
@patch("os.path.exists", return_value=True)
@patch("readme_command_tester.extract_readme_commands", return_value=[])
def test_main_no_commands(mock_extract, mock_exists):
    with pytest.raises(SystemExit) as excinfo:
        readme_command_tester.main()
    assert excinfo.value.code == 0


@patch("sys.argv", ["readme_command_tester.py", "README.md", "-d"])
@patch("os.path.exists", return_value=True)
@patch("readme_command_tester.extract_readme_commands", return_value=["echo 1"])
def test_main_dry_run(mock_extract, mock_exists):
    with pytest.raises(SystemExit) as excinfo:
        readme_command_tester.main()
    assert excinfo.value.code == 0


@patch("sys.argv", ["readme_command_tester.py", "README.md"])
@patch("os.path.exists", return_value=True)
@patch("readme_command_tester.extract_readme_commands", return_value=["echo 1"])
@patch("readme_command_tester.run_commands_in_sandbox")
@patch("tempfile.TemporaryDirectory")
def test_main_execution_success(
    mock_tempdir, mock_run_sandbox, mock_extract, mock_exists
):
    mock_tempdir.return_value.__enter__.return_value = "/sandbox"
    mock_run_sandbox.return_value = [
        {"command": "echo 1", "exit_code": 0, "stdout": "1", "stderr": ""}
    ]

    # Success doesn't call sys.exit, it returns cleanly
    readme_command_tester.main()


@patch("sys.argv", ["readme_command_tester.py", "README.md"])
@patch("os.path.exists", return_value=True)
@patch("readme_command_tester.extract_readme_commands", return_value=["echo 1"])
@patch("readme_command_tester.run_commands_in_sandbox")
@patch("tempfile.TemporaryDirectory")
def test_main_execution_failed(
    mock_tempdir, mock_run_sandbox, mock_extract, mock_exists
):
    mock_tempdir.return_value.__enter__.return_value = "/sandbox"
    mock_run_sandbox.return_value = [
        {"command": "echo 1", "exit_code": 1, "stdout": "", "stderr": "error"}
    ]

    with pytest.raises(SystemExit) as excinfo:
        readme_command_tester.main()
    assert excinfo.value.code == 1

"""Unit tests for command-doctor utility."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "checkers/command-doctor")

# pylint: disable=import-error,wrong-import-position
from command_doctor import (  # noqa: E402
    CommandDoctor,
    check_executable,
    check_missing_files,
    check_path_anomalies,
    check_permissions,
    check_port_conflicts,
    check_virtual_env,
    main,
)


def test_check_executable() -> None:
    """Test detecting missing command executables."""
    # Test valid executable (should be found, e.g. python / sys.executable)
    exe_name = os.path.basename(sys.executable)
    assert check_executable(exe_name) is None

    # Test nonexistent executable
    assert check_executable("nonexistent-app") is not None

    # Test relative path nonexistent
    rel_nonexistent = os.path.join(".", "nonexistent-app")
    assert check_executable(rel_nonexistent) is not None


def test_check_missing_files() -> None:
    """Test checking for nonexistent file argument parameters."""
    with patch("os.path.exists") as mock_exists:
        # Mock CWD file missing
        mock_exists.return_value = False
        res = check_missing_files("python script.py data.csv")
        assert len(res) == 2
        assert "does not exist in the CWD" in res[0]

        # Mock alternate path existing (separator check)
        test_path = "data/data.csv" if os.path.sep == "\\" else "data\\data.csv"
        alt_path = test_path.replace("\\", "/").replace("/", os.path.sep)

        mock_exists.side_effect = lambda p: p == "script.py" or p == alt_path
        res = check_missing_files(f"python script.py {test_path}")
        assert len(res) == 1
        assert "Check path separators" in res[0]


def test_check_permissions() -> None:
    """Test mapping file permission errors from stderr tracebacks."""
    assert (
        check_permissions("PermissionError: [Errno 13] Permission denied") is not None
    )
    assert check_permissions("Access is denied.") is not None
    assert check_permissions("File successfully loaded") is None


def test_check_port_conflicts() -> None:
    """Test analyzing socket address binding conflict tracebacks."""
    # No binding conflict in stderr
    assert check_port_conflicts("Connection refused") is None

    # Conflict in stderr (port 8080)
    stderr = "OSError: [Errno 98] Address already in use: ('0.0.0.0', 8080)"

    with patch("psutil.net_connections") as mock_conns, patch(
        "psutil.Process"
    ) as mock_proc:

        # Setup mock connection
        mock_conn = MagicMock()
        mock_conn.laddr.port = 8080
        mock_conn.pid = 9999
        mock_conns.return_value = [mock_conn]

        # Setup mock process
        mock_p = MagicMock()
        mock_p.name.return_value = "python"
        mock_p.cmdline.return_value = ["python", "app.py"]
        mock_p.exe.return_value = "/bin/python"
        mock_proc.return_value = mock_p

        res = check_port_conflicts(stderr)
        assert res is not None
        assert "Port: 8080" in res
        assert "Owner Process: 'python'" in res
        assert "(PID: 9999)" in res


def test_check_virtual_env() -> None:
    """Test diagnosing venv execution setups."""
    # Test ModuleNotFoundError
    stderr = "ModuleNotFoundError: No module named 'requests'"
    res = check_virtual_env("python script.py", stderr)
    assert len(res) == 1
    assert "failed to import module 'requests'" in res[0]

    # Test venv mismatch warning (runs python outside of venv but .venv is present)
    with patch("os.path.isdir") as mock_isdir, patch("sys.prefix", "/global"), patch(
        "sys.base_prefix", "/global"
    ), patch("os.environ", {}):

        mock_isdir.side_effect = lambda d: d == ".venv"
        res = check_virtual_env("python script.py", "Traceback error")
        assert len(res) == 1
        assert "local virtual environment is present" in res[0]


def test_check_path_anomalies() -> None:
    """Test verifying PATH directory entries for duplicates and missing folders."""
    with patch(
        "os.environ", {"PATH": f"dir_a{os.pathsep}dir_a{os.pathsep}dir_b"}
    ), patch("os.path.isdir") as mock_isdir:

        # dir_a is valid, dir_b is invalid
        mock_isdir.side_effect = lambda d: d == "dir_a"

        res = check_path_anomalies()
        assert any("Duplicate PATH entry detected" in r for r in res)
        assert any("does not exist" in r for r in res)


@patch("subprocess.run")
@patch("shutil.which")
def test_command_doctor_diagnose(mock_which: MagicMock, mock_run: MagicMock) -> None:
    """Test running the doctor rules engine against a failed process execution."""
    mock_which.return_value = "/usr/bin/python"

    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stdout = ""
    mock_res.stderr = "PermissionError: Permission denied"
    mock_run.return_value = mock_res

    doctor = CommandDoctor(command="python script.py")
    result = doctor.diagnose()

    assert result["exit_code"] == 1
    assert any("permission failure" in issue for issue in result["issues"])
    assert any("run as administrator" in rec for rec in result["recommendations"])


@patch("command_doctor.CommandDoctor.diagnose")
def test_main_cli(mock_diag: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    """Test Command Doctor main CLI command interface."""
    mock_diag.return_value = {
        "issues": ["Executable is not in PATH"],
        "recommendations": ["Check executable spelling"],
        "exit_code": 1,
        "stdout": "",
        "stderr": "",
    }

    with patch("sys.argv", ["command-doctor", "-c", "nonexistent-app"]):
        main()
        captured = capsys.readouterr()
        assert "COMMAND DIAGNOSTIC REPORT" in captured.out
        assert "Executable is not in PATH" in captured.out
        assert "Check executable spelling" in captured.out

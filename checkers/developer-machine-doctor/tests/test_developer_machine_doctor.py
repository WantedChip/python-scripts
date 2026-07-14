"""Unit tests for Developer Machine Doctor."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Insert src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from developer_machine_doctor.main import (  # noqa: E402
    check_disk_space,
    check_path_env,
    check_permissions,
    check_port_conflicts,
    check_python_env,
    check_system_dependencies,
    get_program_version,
    main,
    print_report,
)


@pytest.fixture
def mock_env():
    """Fixture to mock environment variables."""
    path_sep = ";" if sys.platform == "win32" else ":"
    mock_path = path_sep.join(["/usr/bin", "/invalid/path", "/usr/bin"])
    with patch.dict("os.environ", {"PATH": mock_path}):
        yield


def test_check_path_env(mock_env) -> None:
    """Test PATH diagnostics parser."""
    with patch.object(Path, "exists") as mock_exists, patch.object(
        Path, "is_dir"
    ) as mock_is_dir:
        # Mock existence
        def exists_side_effect(*args, **kwargs):
            if args:
                return "/usr/bin" in str(args[0]).replace("\\", "/")
            return False

        mock_exists.side_effect = exists_side_effect
        mock_is_dir.side_effect = exists_side_effect

        report = check_path_env()
        assert report["total_count"] == 3
        # Duplicate should find the duplicate "/usr/bin"
        assert "/usr/bin" in report["duplicates"]
        # Invalid dir "/invalid/path"
        assert "/invalid/path" in report["invalid_dirs"]
        assert len(report["warnings"]) == 2


def test_get_program_version() -> None:
    """Test version query function."""
    with patch("shutil.which") as mock_which, patch("subprocess.run") as mock_run:
        # 1. Not installed
        mock_which.return_value = None
        assert get_program_version("git", ["--version"]) is None

        # 2. Installed, normal output
        mock_which.return_value = "/usr/bin/git"
        mock_subproc = MagicMock()
        mock_subproc.stdout = "git version 2.30.1\n"
        mock_subproc.stderr = ""
        mock_run.return_value = mock_subproc

        assert get_program_version("git", ["--version"]) == "git version 2.30.1"


def test_check_python_env() -> None:
    """Test Python interpreter diagnostics."""
    with patch("sys.prefix", "venv_path"), patch("sys.base_prefix", "base_path"), patch(
        "shutil.which", return_value=None
    ):
        # Mocks virtual environment detection
        report = check_python_env()
        assert report["in_virtualenv"] is True
        assert "package_managers" in report


def test_check_system_dependencies() -> None:
    """Test dependency check logic."""
    with patch("shutil.which") as mock_which, patch(
        "developer_machine_doctor.main.get_program_version"
    ) as mock_get_ver:
        # Mock git present, others missing
        mock_which.side_effect = lambda x: "/usr/bin/git" if x == "git" else None
        mock_get_ver.return_value = "git version 2.30.0"

        report = check_system_dependencies()
        assert "git" in report["present"]
        assert report["present"]["git"]["path"] == "/usr/bin/git"
        assert "docker" in report["missing"]


def test_check_port_conflicts() -> None:
    """Test socket binds and port conflict detection."""
    # We mock sockets to raise error for ports 80 and 8080 (meaning they are in use)
    # and bind successfully for others.
    with patch("socket.socket") as mock_sock:
        mock_instance = MagicMock()
        mock_sock.return_value.__enter__.return_value = mock_instance

        def bind_side_effect(addr):
            port = addr[1]
            if port in [80, 8080]:
                raise OSError("Address already in use")

        mock_instance.bind.side_effect = bind_side_effect

        # Mock psutil
        with patch("developer_machine_doctor.main.psutil") as mock_psutil:
            mock_psutil.net_connections.return_value = []

            # Perform check
            report = check_port_conflicts([80, 443, 8080])

            # Port 80 and 8080 should be marked as occupied
            assert 80 in report
            assert 8080 in report
            assert 443 not in report
            assert report[80]["pid"] == -1  # psutil connection list was empty


def test_check_disk_space() -> None:
    """Test disk utilization reporter."""
    with patch("shutil.disk_usage") as mock_disk:
        mock_usage = MagicMock()
        mock_usage.total = 100 * 1024**3
        mock_usage.used = 40 * 1024**3
        mock_usage.free = 60 * 1024**3
        mock_disk.return_value = mock_usage

        report = check_disk_space()
        assert report["total_gb"] == 100.0
        assert report["used_gb"] == 40.0
        assert report["free_gb"] == 60.0
        assert report["usage_percent"] == 40.0
        assert report["error"] is None


def test_check_permissions() -> None:
    """Test administrative privileges diagnostic checks."""
    with patch("platform.system", return_value="Linux"), patch(
        "os.getuid", return_value=0, create=True
    ):
        report = check_permissions()
        assert report["is_admin"] is True


def test_cli_execution_json() -> None:
    """Test CLI execution and JSON report generation."""
    test_args = ["developer_machine_doctor", "--json", "--ports", "8080"]

    with patch.object(sys, "argv", test_args), patch("sys.stdout.write") as mock_write:
        main()
        # Ensure some JSON was written
        assert mock_write.called
        written_string = "".join(
            call.args[0] for call in mock_write.call_args_list if call.args
        )
        data = json.loads(written_string)
        assert "path" in data
        assert "python" in data


def test_print_report(capsys) -> None:
    """Test standard text print report output formatting."""
    report = {
        "path": {
            "total_count": 5,
            "duplicates": ["/usr/bin"],
            "invalid_dirs": ["/invalid/path"],
            "warnings": ["warning 1", "warning 2"],
        },
        "python": {
            "python_version": "3.12.0",
            "interpreter": "/usr/bin/python",
            "in_virtualenv": True,
            "virtualenv_path": "/path/to/venv",
            "package_managers": {"pip": "22.0.0"},
        },
        "dependencies": {
            "present": {"git": {"path": "/usr/bin/git", "version": "2.30.0"}},
            "missing": ["docker"],
        },
        "ports": {
            80: {
                "pid": 1234,
                "name": "nginx",
                "command": "nginx -g daemon off;",
                "username": "root",
                "status": "LISTEN",
            },
            443: {
                "pid": -1,
                "name": "Occupied (Details unavailable)",
                "command": "",
                "username": "",
                "status": "LISTEN",
            },
        },
        "disk": {
            "total_gb": 100.0,
            "used_gb": 95.0,
            "free_gb": 5.0,
            "usage_percent": 95.0,
            "error": None,
        },
        "permissions": {
            "is_admin": True,
            "temp_writable": True,
            "workspace_writable": True,
        },
    }
    print_report(report)
    captured = capsys.readouterr()
    assert "DEVELOPER MACHINE DIAGNOSTIC REPORT" in captured.out
    assert "Duplicate directories found" in captured.out
    assert "nginx" in captured.out
    assert "WARNING: High disk utilization" in captured.out


def test_cli_execution_text(capsys) -> None:
    """Test text report mode execution in main."""
    test_args = ["developer_machine_doctor", "--ports", "80"]
    with patch.object(sys, "argv", test_args), patch(
        "developer_machine_doctor.main.check_port_conflicts"
    ) as mock_ports:
        mock_ports.return_value = {
            80: {
                "pid": 1234,
                "name": "nginx",
                "command": "nginx",
                "username": "root",
                "status": "LISTEN",
            }
        }
        main()

    captured = capsys.readouterr()
    assert "DEVELOPER MACHINE DIAGNOSTIC REPORT" in captured.out
    assert "Port 80 is occupied" in captured.out


def test_cli_invalid_ports() -> None:
    """Test error handler for malformed ports list string."""
    test_args = ["developer_machine_doctor", "--ports", "invalid_port"]
    with patch.object(sys, "argv", test_args), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_check_port_conflicts_with_psutil() -> None:
    """Test port diagnostics process mapping via psutil."""
    with patch("socket.socket") as mock_sock, patch(
        "developer_machine_doctor.main.psutil"
    ) as mock_psutil:
        mock_instance = MagicMock()
        mock_sock.return_value.__enter__.return_value = mock_instance
        # Mock port 8080 to raise OSError (in use)
        mock_instance.bind.side_effect = OSError("Address already in use")

        mock_conn = MagicMock()
        mock_conn.laddr.port = 8080
        mock_conn.pid = 1234
        mock_conn.status = "LISTEN"
        mock_psutil.net_connections.return_value = [mock_conn]

        mock_proc = MagicMock()
        mock_proc.name.return_value = "python"
        mock_proc.cmdline.return_value = ["python", "app.py"]
        mock_proc.username.return_value = "user"
        mock_psutil.Process.return_value = mock_proc

        report = check_port_conflicts([8080])
        assert 8080 in report
        assert report[8080]["pid"] == 1234
        assert report[8080]["name"] == "python"
        assert report[8080]["command"] == "python app.py"

"""Unit tests for port-story utility."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/port-story")

# pylint: disable=import-error,wrong-import-position
import psutil  # noqa: E402
from port_story import (  # noqa: E402
    PortStory,
    get_database_heuristics,
    get_dev_server_heuristics,
    get_docker_heuristics,
    get_process_story,
    get_system_service_heuristics,
    main,
    render_report,
    sanitize_env_vars,
)


def test_sanitize_env_vars() -> None:
    """Test environment variable masking of sensitive keys."""
    env = {
        "PATH": "/bin:/usr/bin",
        "DATABASE_URL": "postgres://user:pass@host/db",
        "MY_AWS_SECRET": "secret123",
        "PORT": "8080",
    }
    sanitized = sanitize_env_vars(env)
    assert sanitized["PATH"] == "/bin:/usr/bin"
    assert sanitized["DATABASE_URL"] == "[SANITIZED]"
    assert sanitized["MY_AWS_SECRET"] == "[SANITIZED]"
    assert sanitized["PORT"] == "8080"


def test_get_docker_heuristics() -> None:
    """Test Docker process association heuristics detection."""
    proc = MagicMock()
    proc.name.return_value = "docker-proxy"
    proc.cmdline.return_value = ["/usr/bin/docker-proxy", "-proto", "tcp"]
    assert get_docker_heuristics(proc) is True

    # Test normal python process
    proc_normal = MagicMock()
    proc_normal.name.return_value = "python"
    proc_normal.cmdline.return_value = ["python", "app.py"]
    proc_normal.parent.return_value = None
    assert get_docker_heuristics(proc_normal) is False

    # Test parent exception
    proc_err = MagicMock()
    proc_err.name.return_value = "python"
    proc_err.parent.side_effect = psutil.AccessDenied()
    assert get_docker_heuristics(proc_err) is False


def test_get_dev_server_heuristics() -> None:
    """Test local development servers heuristics mapping."""
    proc = MagicMock()
    proc.cmdline.return_value = ["node", "node_modules/vite/bin/vite.js"]
    proc.exe.return_value = "/usr/bin/node"
    assert get_dev_server_heuristics(proc) is True

    # Test normal python process
    proc_normal = MagicMock()
    proc_normal.cmdline.return_value = ["python", "app.py"]
    proc_normal.exe.return_value = "/usr/bin/python"
    assert get_dev_server_heuristics(proc_normal) is False

    # Test exception handling
    proc_err = MagicMock()
    proc_err.cmdline.side_effect = psutil.NoSuchProcess(123)
    assert get_dev_server_heuristics(proc_err) is False


def test_get_database_heuristics() -> None:
    """Test database process heuristics checks."""
    proc = MagicMock()
    proc.name.return_value = "postgres"
    proc.cmdline.return_value = ["postgres", "-D", "/var/lib/postgresql/data"]
    assert get_database_heuristics(proc) is True

    # Test exception handling
    proc_err = MagicMock()
    proc_err.name.side_effect = psutil.AccessDenied()
    assert get_database_heuristics(proc_err) is False


def test_get_system_service_heuristics() -> None:
    """Test daemon/service account checks."""
    proc = MagicMock()
    proc.username.return_value = "root"
    assert get_system_service_heuristics(proc) is True

    proc_user = MagicMock()
    proc_user.username.return_value = "dev"
    proc_user.parent.return_value = None
    assert get_system_service_heuristics(proc_user) is False

    # Test exception handling
    proc_err = MagicMock()
    proc_err.username.side_effect = psutil.AccessDenied()
    assert get_system_service_heuristics(proc_err) is False


def test_get_process_story() -> None:
    """Test compiling process history reports and metadata checks."""
    proc = MagicMock()
    proc.pid = 1234
    proc.name.return_value = "python"
    proc.exe.return_value = "/bin/python"
    proc.cwd.return_value = "/work"
    proc.username.return_value = "dev"
    proc.cmdline.return_value = ["python", "app.py"]
    proc.create_time.return_value = 1774872000.0  # Dec 2026
    proc.parent.return_value = None

    story = get_process_story(proc, verbose=False)
    assert story["pid"] == 1234
    assert story["name"] == "python"
    assert story["exe"] == "/bin/python"
    assert story["cwd"] == "/work"
    assert story["username"] == "dev"
    assert "2026-" in story["start_time"]
    assert "Dev Server" not in story["tags"]


def test_get_process_story_access_denied() -> None:
    """Test process story handles psutil.AccessDenied gracefully."""
    proc = MagicMock()
    proc.pid = 9999
    proc.name.side_effect = psutil.AccessDenied()
    proc.exe.side_effect = psutil.AccessDenied()
    proc.cwd.side_effect = psutil.AccessDenied()
    proc.username.side_effect = psutil.AccessDenied()
    proc.cmdline.side_effect = psutil.AccessDenied()
    proc.create_time.side_effect = psutil.AccessDenied()
    proc.parent.side_effect = psutil.AccessDenied()
    proc.environ.side_effect = psutil.AccessDenied()

    story = get_process_story(proc, verbose=True)
    assert story["pid"] == 9999
    assert story["exe"] == ""
    assert story["cwd"] == ""
    assert story["environment"] == {
        "error": "Access Denied reading environment variables."
    }


@patch("psutil.net_connections")
@patch("psutil.Process")
def test_port_story_scan(mock_proc_cls: MagicMock, mock_conns: MagicMock) -> None:
    """Test PortStory scans mapping connection records to process histories."""
    # Setup mock TCP connection list
    mock_conn = MagicMock()
    mock_conn.laddr.port = 8080
    mock_conn.laddr.ip = "127.0.0.1"
    mock_conn.raddr = None
    mock_conn.status = "LISTEN"
    mock_conn.pid = 1234
    mock_conns.return_value = [mock_conn]

    # Setup process details
    mock_proc = MagicMock()
    mock_proc.pid = 1234
    proc_name = "node"
    mock_proc.name.return_value = proc_name
    mock_proc.exe.return_value = "/usr/bin/node"
    mock_proc.cwd.return_value = "/app"
    mock_proc.username.return_value = "node_user"
    mock_proc.cmdline.return_value = ["node", "server.js"]
    mock_proc.create_time.return_value = 1774872000.0
    mock_proc.parent.return_value = None
    mock_proc_cls.return_value = mock_proc

    scanner = PortStory(ports=[8080])
    results = scanner.scan(verbose=True)

    assert len(results) == 1
    assert results[0]["port"] == 8080
    assert results[0]["local_address"] == "127.0.0.1:8080"
    assert results[0]["process"]["pid"] == 1234
    assert results[0]["process"]["name"] == "node"


@patch("port_story.PortStory.scan")
def test_main_cli(mock_scan: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    """Test Command CLI interfaces."""
    mock_scan.return_value = [
        {
            "port": 8080,
            "status": "LISTEN",
            "local_address": "127.0.0.1:8080",
            "remote_address": "N/A",
            "process": {
                "pid": 1234,
                "name": "python",
                "exe": "/bin/python",
                "cwd": "/work",
                "username": "dev",
                "cmdline": ["python", "server.py"],
                "parent": None,
                "tags": ["Dev Server"],
                "start_time": "2026-07-15 12:00:00",
                "environment": {},
            },
        }
    ]

    with patch("sys.argv", ["port-story", "8080"]):
        main()
        captured = capsys.readouterr()
        assert "PORT STORY REPORT" in captured.out
        assert "Port 8080 [LISTEN]" in captured.out
        assert "Dev Server" in captured.out


@patch("port_story.PortStory.scan")
def test_main_json(mock_scan: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    """Test main function JSON output flags."""
    mock_scan.return_value = [{"port": 80, "status": "LISTEN", "process": None}]

    with patch("sys.argv", ["port-story", "--json"]):
        main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 1
        assert data[0]["port"] == 80


def test_render_report_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """Test rendering report when list is empty."""
    render_report([])
    captured = capsys.readouterr()
    assert "No active ports matched the target scan." in captured.out


@patch("port_story.psutil", None)
def test_main_no_psutil(capsys: pytest.CaptureFixture[str]) -> None:
    """Test exit status when psutil package is not imported."""
    with patch("sys.argv", ["port-story"]), pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "psutil' package is required" in captured.out


@patch("port_story.psutil", None)
def test_scan_no_psutil() -> None:
    """Test scanner returns empty list if psutil package is not imported."""
    scanner = PortStory([80])
    assert scanner.scan() == []

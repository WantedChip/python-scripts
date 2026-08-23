import os
import sys
from unittest.mock import MagicMock, patch

import pytest


# Mock psutil in sys.modules so imports and patches work even if psutil isn't installed
class MockPsutilError(Exception):
    pass


mock_psutil = MagicMock()
mock_psutil.Error = MockPsutilError
sys.modules["psutil"] = mock_psutil

# Add target directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import port_conflict_doctor  # noqa: E402


def test_check_docker_containers_matches():
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = (
        "cid1|name1|:8080->80/tcp\ncid2|name2|0.0.0.0:9090->90/tcp\ncid3|name3|other"
    )

    with patch("subprocess.run", return_value=mock_run):
        res = port_conflict_doctor.check_docker_containers(8080)
        assert len(res) == 1
        assert "cid1|name1|:8080->80/tcp" in res[0]

        res = port_conflict_doctor.check_docker_containers(9090)
        assert len(res) == 1
        assert "cid2|name2|0.0.0.0:9090->90/tcp" in res[0]

        res = port_conflict_doctor.check_docker_containers(7070)
        assert len(res) == 0


def test_check_docker_containers_failure():
    with patch("subprocess.run", side_effect=OSError("command not found")):
        res = port_conflict_doctor.check_docker_containers(8080)
        assert res == []


def test_diagnose_port_docker_only(capsys):
    with patch(
        "port_conflict_doctor.check_docker_containers",
        return_value=["cid123|my-nginx|0.0.0.0:8080->80/tcp"],
    ), patch("port_conflict_doctor.psutil.net_connections", return_value=[]):
        port_conflict_doctor.diagnose_port(8080)

        captured = capsys.readouterr()
        assert "DIAGNOSING PORT CONFLICT: 8080" in captured.out
        assert "PORT CONFLICT DETECTED IN DOCKER CONTAINER:" in captured.out
        assert "Container ID:   cid123" in captured.out
        assert "Container Name: my-nginx" in captured.out
        assert "Port Mapping:   0.0.0.0:8080->80/tcp" in captured.out
        assert "docker stop cid123" in captured.out


def test_diagnose_port_local_process_win32(capsys):
    mock_conn = MagicMock()
    mock_conn.laddr.port = 8080
    mock_conn.status = "LISTEN"
    mock_conn.pid = 1234

    mock_parent = MagicMock()
    mock_parent.name.return_value = "cmd.exe"
    mock_parent.pid = 1000

    mock_proc = MagicMock()
    mock_proc.name.return_value = "python.exe"
    mock_proc.cwd.return_value = "C:\\my-app"
    mock_proc.cmdline.return_value = ["python", "app.py"]
    mock_proc.parent.return_value = mock_parent

    with patch("port_conflict_doctor.check_docker_containers", return_value=[]), patch(
        "port_conflict_doctor.psutil.net_connections", return_value=[mock_conn]
    ), patch("port_conflict_doctor.psutil.Process", return_value=mock_proc), patch(
        "sys.platform", "win32"
    ):
        port_conflict_doctor.diagnose_port(8080)

        captured = capsys.readouterr()
        assert "LOCAL PROCESS DETECTED (PID 1234):" in captured.out
        assert "Process Name:     python.exe" in captured.out
        assert "Working Dir:      C:\\my-app" in captured.out
        assert "Launch Command:   python app.py" in captured.out
        assert "Parent Process:   cmd.exe (PID 1000)" in captured.out
        assert "taskkill /F /PID 1234" in captured.out


def test_diagnose_port_local_process_unix(capsys):
    mock_conn = MagicMock()
    mock_conn.laddr.port = 8080
    mock_conn.status = "LISTEN"
    mock_conn.pid = 1234

    mock_proc = MagicMock()
    mock_proc.name.return_value = "node"
    mock_proc.cwd.return_value = "/app"
    mock_proc.cmdline.return_value = ["node", "server.js"]
    mock_proc.parent.return_value = None

    with patch("port_conflict_doctor.check_docker_containers", return_value=[]), patch(
        "port_conflict_doctor.psutil.net_connections", return_value=[mock_conn]
    ), patch("port_conflict_doctor.psutil.Process", return_value=mock_proc), patch(
        "sys.platform", "linux"
    ):
        port_conflict_doctor.diagnose_port(8080)

        captured = capsys.readouterr()
        assert "LOCAL PROCESS DETECTED (PID 1234):" in captured.out
        assert "Process Name:     node" in captured.out
        assert "Working Dir:      /app" in captured.out
        assert "Launch Command:   node server.js" in captured.out
        assert "Parent Process:   N/A (PID N/A)" in captured.out
        assert "kill -9 1234" in captured.out


def test_diagnose_port_local_process_no_pid(capsys):
    mock_conn = MagicMock()
    mock_conn.laddr.port = 8080
    mock_conn.status = "LISTEN"
    mock_conn.pid = None

    with patch("port_conflict_doctor.check_docker_containers", return_value=[]), patch(
        "port_conflict_doctor.psutil.net_connections", return_value=[mock_conn]
    ):
        port_conflict_doctor.diagnose_port(8080)

        captured = capsys.readouterr()
        assert "Port is listening but process ID could not be resolved" in captured.out


def test_diagnose_port_local_process_permission_error(capsys):
    mock_conn = MagicMock()
    mock_conn.laddr.port = 8080
    mock_conn.status = "LISTEN"
    mock_conn.pid = 1234

    with patch("port_conflict_doctor.check_docker_containers", return_value=[]), patch(
        "port_conflict_doctor.psutil.net_connections", return_value=[mock_conn]
    ), patch(
        "port_conflict_doctor.psutil.Process", side_effect=OSError("Access Denied")
    ):
        port_conflict_doctor.diagnose_port(8080)

        captured = capsys.readouterr()
        assert "Failed to read process 1234 details: Access Denied" in captured.out


def test_diagnose_port_free(capsys):
    with patch("port_conflict_doctor.check_docker_containers", return_value=[]), patch(
        "port_conflict_doctor.psutil.net_connections", return_value=[]
    ):
        port_conflict_doctor.diagnose_port(8080)

        captured = capsys.readouterr()
        assert "Port 8080 appears to be free and available for use." in captured.out


def test_main_no_psutil(capsys):
    with patch("port_conflict_doctor.HAS_PSUTIL", False), patch(
        "sys.argv", ["port_conflict_doctor.py", "8080"]
    ), pytest.raises(SystemExit) as exc_info:
        port_conflict_doctor.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "The 'psutil' package is required" in captured.err


def test_main_with_port():
    with patch("port_conflict_doctor.HAS_PSUTIL", True), patch(
        "sys.argv", ["port_conflict_doctor.py", "8080"]
    ), patch("port_conflict_doctor.diagnose_port") as mock_diag:
        port_conflict_doctor.main()
        mock_diag.assert_called_once_with(8080)


def test_main_no_port_scan_empty(capsys):
    with patch("port_conflict_doctor.HAS_PSUTIL", True), patch(
        "sys.argv", ["port_conflict_doctor.py"]
    ), patch(
        "port_conflict_doctor.psutil.net_connections", return_value=[]
    ), pytest.raises(
        SystemExit
    ) as exc_info:
        port_conflict_doctor.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "No active listening ports discovered" in captured.out


def test_main_no_port_scan_with_selection():
    mock_conn1 = MagicMock()
    mock_conn1.status = "LISTEN"
    mock_conn1.laddr.port = 8080
    mock_conn2 = MagicMock()
    mock_conn2.status = "LISTEN"
    mock_conn2.laddr.port = 9090

    with patch("port_conflict_doctor.HAS_PSUTIL", True), patch(
        "sys.argv", ["port_conflict_doctor.py"]
    ), patch(
        "port_conflict_doctor.psutil.net_connections",
        return_value=[mock_conn1, mock_conn2],
    ), patch(
        "builtins.input", return_value="9090"
    ), patch(
        "port_conflict_doctor.diagnose_port"
    ) as mock_diag:
        port_conflict_doctor.main()
        mock_diag.assert_called_once_with(9090)


def test_main_no_port_scan_abort(capsys):
    mock_conn = MagicMock()
    mock_conn.status = "LISTEN"
    mock_conn.laddr.port = 8080

    with patch("port_conflict_doctor.HAS_PSUTIL", True), patch(
        "sys.argv", ["port_conflict_doctor.py"]
    ), patch(
        "port_conflict_doctor.psutil.net_connections", return_value=[mock_conn]
    ), patch(
        "builtins.input", side_effect=KeyboardInterrupt
    ), pytest.raises(
        SystemExit
    ) as exc_info:
        port_conflict_doctor.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Operation aborted." in captured.out

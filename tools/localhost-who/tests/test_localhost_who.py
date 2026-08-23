import os
import sys
from unittest.mock import MagicMock

import pytest


# Create a mock psutil module so that tests run successfully even if psutil
# is not installed.
class MockPsutilError(Exception):
    pass


class MockAccessDenied(MockPsutilError):
    pass


class MockNoSuchProcess(MockPsutilError):
    pass


mock_psutil = MagicMock()
sys.modules["psutil"] = mock_psutil
mock_psutil.Error = MockPsutilError
mock_psutil.AccessDenied = MockAccessDenied
mock_psutil.NoSuchProcess = MockNoSuchProcess

# Add parent directory to sys.path so we can import the script
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from unittest.mock import patch  # noqa: E402

from localhost_who import check_port_health, main  # noqa: E402


@patch("urllib.request.urlopen")
def test_check_port_health_healthy(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    assert check_port_health(8080) == "Healthy (200)"


@patch("urllib.request.urlopen")
def test_check_port_health_http_error(mock_urlopen):
    err = urllib.error.HTTPError("http://localhost:8080/", 403, "Forbidden", {}, None)
    mock_urlopen.side_effect = err

    assert check_port_health(8080) == "Responsive (403)"


@patch("socket.create_connection")
@patch("urllib.request.urlopen")
def test_check_port_health_tcp_open(mock_urlopen, mock_socket_conn):
    mock_urlopen.side_effect = OSError("Not HTTP")
    mock_socket_conn.return_value.__enter__.return_value = MagicMock()

    assert check_port_health(8080) == "TCP Open (No HTTP)"


@patch("socket.create_connection")
@patch("urllib.request.urlopen")
def test_check_port_health_unreachable(mock_urlopen, mock_socket_conn):
    mock_urlopen.side_effect = OSError("Not HTTP")
    mock_socket_conn.side_effect = OSError("Connection refused")

    assert check_port_health(8080) == "Unreachable"


@patch("sys.argv", ["localhost_who.py"])
@patch("localhost_who.HAS_PSUTIL", False)
@patch("sys.exit")
@patch("sys.stderr")
def test_main_no_psutil(mock_stderr, mock_exit):
    mock_exit.side_effect = SystemExit
    with pytest.raises(SystemExit):
        main()
    mock_exit.assert_called_once_with(1)


@patch("sys.argv", ["localhost_who.py"])
@patch("localhost_who.HAS_PSUTIL", True)
@patch("localhost_who.psutil.net_connections")
@patch("sys.exit")
@patch("builtins.print")
def test_main_no_listeners(mock_print, mock_exit, mock_net_conns):
    mock_net_conns.return_value = []
    mock_exit.side_effect = SystemExit
    with pytest.raises(SystemExit):
        main()
    mock_exit.assert_called_once_with(0)


@patch("sys.argv", ["localhost_who.py"])
@patch("localhost_who.HAS_PSUTIL", True)
@patch("localhost_who.psutil.net_connections")
@patch("sys.exit")
@patch("sys.stderr")
def test_main_net_connections_error(mock_stderr, mock_exit, mock_net_conns):
    mock_net_conns.side_effect = OSError("Read error")
    mock_exit.side_effect = SystemExit
    with pytest.raises(SystemExit):
        main()
    mock_exit.assert_called_once_with(1)


@patch("sys.argv", ["localhost_who.py"])
@patch("localhost_who.HAS_PSUTIL", True)
@patch("localhost_who.psutil.net_connections")
@patch("localhost_who.psutil.Process")
@patch("localhost_who.check_port_health")
@patch("localhost_who.datetime")
@patch("builtins.print")
def test_main_with_listeners(
    mock_print, mock_datetime, mock_health, mock_process, mock_net_conns
):
    mock_time = 1700000000.0
    mock_now = MagicMock()
    mock_now.timestamp.return_value = mock_time
    mock_datetime.now.return_value = mock_now

    conn1 = MagicMock()
    conn1.status = "LISTEN"
    conn1.laddr.port = 3000
    conn1.pid = 1001

    conn2 = MagicMock()
    conn2.status = "LISTEN"
    conn2.laddr.port = 80
    conn2.pid = 1002

    conn3 = MagicMock()
    conn3.status = "LISTEN"
    conn3.laddr.port = 2000
    conn3.pid = 1003

    conn4 = MagicMock()
    conn4.status = "LISTEN"
    conn4.laddr.port = 3000
    conn4.pid = 1001

    conn5 = MagicMock()
    conn5.status = "ESTABLISHED"
    conn5.laddr.port = 8080
    conn5.pid = 1004

    mock_net_conns.return_value = [conn1, conn2, conn3, conn4, conn5]

    proc1 = MagicMock()
    proc1.create_time.return_value = mock_time - 30
    proc1.cmdline.return_value = ["node", "app.js"]
    proc1.cwd.return_value = "/workspace/my-project"
    proc1.name.return_value = "node"

    proc2 = MagicMock()
    proc2.create_time.return_value = mock_time - 180
    proc2.cmdline.return_value = ["python", "manage.py", "runserver"]
    proc2.cwd.return_value = None
    proc2.name.return_value = "python"

    conn_hours = MagicMock()
    conn_hours.status = "LISTEN"
    conn_hours.laddr.port = 8080
    conn_hours.pid = 1005
    mock_net_conns.return_value.append(conn_hours)

    proc_hours = MagicMock()
    proc_hours.create_time.return_value = mock_time - 7200
    proc_hours.cmdline.return_value = ["java", "-jar", "app.jar"]
    proc_hours.cwd.return_value = "/workspace/java-app"
    proc_hours.name.return_value = "java"

    conn_err = MagicMock()
    conn_err.status = "LISTEN"
    conn_err.laddr.port = 9000
    conn_err.pid = 1006
    mock_net_conns.return_value.append(conn_err)

    def process_side_effect(pid):
        if pid == 1001:
            return proc1
        if pid == 1002:
            return proc2
        if pid == 1005:
            return proc_hours
        raise OSError("Access Denied")

    mock_process.side_effect = process_side_effect

    mock_health.side_effect = lambda port: f"Healthy at {port}"

    main()

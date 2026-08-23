import os
import sys
from unittest.mock import MagicMock


# Create a mock psutil module so that tests run successfully even if psutil
# is not installed.
class MockPsutilError(Exception):
    pass


class MockAccessDenied(MockPsutilError):
    pass


class MockNoSuchProcess(MockPsutilError):
    pass


# Only create and assign if it's not already mock-configured to avoid
# overriding references.
if "psutil" not in sys.modules:
    mock_psutil = MagicMock()
    sys.modules["psutil"] = mock_psutil
else:
    mock_psutil = sys.modules["psutil"]

mock_psutil.Error = MockPsutilError
mock_psutil.AccessDenied = MockAccessDenied
mock_psutil.NoSuchProcess = MockNoSuchProcess

# Add parent directory to sys.path so we can import the script
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from unittest.mock import mock_open, patch  # noqa: E402

from localhost_dashboard import (  # noqa: E402
    check_port_health,
    get_dev_servers,
    guess_framework,
    main,
)


@patch("time.perf_counter", side_effect=[1.0, 1.05])
@patch("urllib.request.urlopen")
def test_check_port_health_success(mock_urlopen, mock_perf):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.reason = "OK"
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    status, latency = check_port_health(8080)
    assert status == "200 OK"
    assert abs(latency - 50.0) < 0.001


@patch("time.perf_counter", side_effect=[1.0, 1.05])
@patch("urllib.request.urlopen")
def test_check_port_health_http_error(mock_urlopen, mock_perf):
    err = urllib.error.HTTPError("http://localhost:8080/", 404, "Not Found", {}, None)
    mock_urlopen.side_effect = err

    status, latency = check_port_health(8080)
    assert status == "404 Not Found"
    assert abs(latency - 50.0) < 0.001


@patch("time.perf_counter", side_effect=[1.0, 1.05])
@patch("urllib.request.urlopen")
def test_check_port_health_url_error_timeout(mock_urlopen, mock_perf):
    err = urllib.error.URLError("timed out")
    mock_urlopen.side_effect = err

    status, latency = check_port_health(8080)
    assert status == "Timeout"
    assert latency == 500.0


@patch("urllib.request.urlopen")
def test_check_port_health_url_error_refused(mock_urlopen):
    err = urllib.error.URLError("Connection refused")
    mock_urlopen.side_effect = err

    status, latency = check_port_health(8080)
    assert status == "Unresponsive"
    assert latency == 0.0


@patch("urllib.request.urlopen")
def test_check_port_health_generic_exception(mock_urlopen):
    mock_urlopen.side_effect = ValueError("Some error")

    status, latency = check_port_health(8080)
    assert status == "Error: Some error"
    assert latency == 0.0


@patch("os.path.exists")
def test_guess_framework_invalid_cwd(mock_exists):
    assert guess_framework("") == "Generic Process"
    assert guess_framework("N/A") == "Generic Process"

    mock_exists.return_value = False
    assert guess_framework("some_path") == "Generic Process"


@patch("os.path.exists")
@patch("os.listdir")
def test_guess_framework_oserror(mock_listdir, mock_exists):
    mock_exists.return_value = True
    mock_listdir.side_effect = OSError("Access denied")
    assert guess_framework("some_path") == "Generic Process"


@patch("os.path.exists")
@patch("os.listdir")
def test_guess_framework_indicators(mock_listdir, mock_exists):
    mock_exists.return_value = True

    mock_listdir.return_value = ["package.json"]
    assert guess_framework("some_path") == "Node.js (npm)"

    mock_listdir.return_value = ["pyproject.toml"]
    assert guess_framework("some_path") == "Python (poetry/pip)"


@patch("os.path.exists")
@patch("os.listdir")
def test_guess_framework_deeper_heuristics(mock_listdir, mock_exists):
    mock_exists.side_effect = lambda path: True
    mock_listdir.return_value = []

    with patch(
        "builtins.open", mock_open(read_data='{"dependencies": {"next": "12.0.0"}}')
    ):
        assert guess_framework("some_path") == "Next.js"

    with patch(
        "builtins.open", mock_open(read_data='{"dependencies": {"react": "18.0.0"}}')
    ):
        assert guess_framework("some_path") == "React/Vite"

    with patch(
        "builtins.open", mock_open(read_data='{"dependencies": {"vue": "3.0.0"}}')
    ):
        assert guess_framework("some_path") == "Vue.js"

    with patch(
        "builtins.open", mock_open(read_data='{"dependencies": {"express": "4.0.0"}}')
    ):
        assert guess_framework("some_path") == "Express.js"

    with patch("builtins.open", mock_open(read_data='{"dependencies": {}}')):
        assert guess_framework("some_path") == "Generic Dev Server"

    with patch("builtins.open", side_effect=OSError("Read error")):
        assert guess_framework("some_path") == "Generic Dev Server"


@patch("localhost_dashboard.HAS_PSUTIL", False)
def test_get_dev_servers_no_psutil():
    assert get_dev_servers() == []


@patch("localhost_dashboard.HAS_PSUTIL", True)
@patch("localhost_dashboard.psutil.net_connections")
def test_get_dev_servers_net_connections_error(mock_net_conns):
    mock_net_conns.side_effect = OSError("error")
    assert get_dev_servers() == []


@patch("localhost_dashboard.HAS_PSUTIL", True)
@patch("localhost_dashboard.psutil.net_connections")
@patch("localhost_dashboard.psutil.Process")
@patch("localhost_dashboard.check_port_health")
@patch("localhost_dashboard.guess_framework")
@patch("time.time")
def test_get_dev_servers_success(
    mock_time, mock_guess, mock_health, mock_process, mock_net_conns
):
    conn1 = MagicMock()
    conn1.status = "LISTEN"
    conn1.laddr.port = 3000
    conn1.pid = 1001

    conn_dup = MagicMock()
    conn_dup.status = "LISTEN"
    conn_dup.laddr.port = 3000
    conn_dup.pid = 1002

    conn_no_pid = MagicMock()
    conn_no_pid.status = "LISTEN"
    conn_no_pid.laddr.port = 4000
    conn_no_pid.pid = None

    conn_not_listen = MagicMock()
    conn_not_listen.status = "ESTABLISHED"
    conn_not_listen.laddr.port = 5000
    conn_not_listen.pid = 1003

    conn2 = MagicMock()
    conn2.status = "LISTEN"
    conn2.laddr.port = 8080
    conn2.pid = 1004

    mock_net_conns.return_value = [conn1, conn_dup, conn_no_pid, conn_not_listen, conn2]

    proc1 = MagicMock()
    proc1.name.return_value = "node"
    proc1.cwd.return_value = "/app"
    proc1.create_time.return_value = 1000.0

    def process_side_effect(pid):
        if pid == 1001:
            return proc1
        raise MockAccessDenied()

    mock_process.side_effect = process_side_effect

    mock_time.return_value = 1100.0
    mock_guess.side_effect = lambda cwd: "Node.js (npm)" if cwd == "/app" else "Unknown"
    mock_health.side_effect = lambda port: (
        ("200 OK", 5.0) if port == 3000 else ("Unresponsive", 0.0)
    )

    servers = get_dev_servers()
    assert len(servers) == 2

    assert servers[0]["port"] == 3000
    assert servers[0]["pid"] == 1001
    assert servers[0]["name"] == "node"
    assert servers[0]["framework"] == "Node.js (npm)"
    assert servers[0]["uptime_sec"] == 100.0
    assert servers[0]["status"] == "200 OK"
    assert servers[0]["latency"] == 5.0

    assert servers[1]["port"] == 8080
    assert servers[1]["pid"] == 1004
    assert servers[1]["name"] == "Access Denied"
    assert servers[1]["framework"] == "Unknown"
    assert servers[1]["uptime_sec"] == 0.0
    assert servers[1]["status"] == "Unresponsive"
    assert servers[1]["latency"] == 0.0


@patch("localhost_dashboard.HAS_PSUTIL", False)
@patch("sys.exit")
@patch("sys.stderr")
def test_main_no_psutil(mock_stderr, mock_exit):
    main()
    mock_exit.assert_called_with(1)


@patch("localhost_dashboard.HAS_PSUTIL", True)
@patch("localhost_dashboard.get_dev_servers")
@patch("sys.argv", ["localhost_dashboard.py"])
@patch("builtins.print")
def test_main_one_shot_with_servers(mock_print, mock_get_servers):
    mock_get_servers.return_value = [
        {
            "port": 3000,
            "pid": 1001,
            "name": "node_server_that_has_a_very_long_name",
            "cwd": "/app",
            "framework": "Node.js (npm)",
            "uptime_sec": 4000.0,
            "status": "200 OK",
            "latency": 5.0,
        },
        {
            "port": 8080,
            "pid": 1002,
            "name": "python",
            "cwd": "/app2",
            "framework": "Python (pip)",
            "uptime_sec": 120.0,
            "status": "Unresponsive",
            "latency": 0.0,
        },
        {
            "port": 9000,
            "pid": 1003,
            "name": "rust",
            "cwd": "/app3",
            "framework": "Rust Server",
            "uptime_sec": 10.0,
            "status": "404 Not Found",
            "latency": 10.0,
        },
    ]
    main()
    mock_get_servers.assert_called_once()


@patch("localhost_dashboard.HAS_PSUTIL", True)
@patch("localhost_dashboard.get_dev_servers", return_value=[])
@patch("sys.argv", ["localhost_dashboard.py"])
@patch("builtins.print")
def test_main_one_shot_empty(mock_print, mock_get_servers):
    main()
    mock_get_servers.assert_called_once()


@patch("localhost_dashboard.HAS_PSUTIL", True)
@patch("localhost_dashboard.get_dev_servers", return_value=[])
@patch("sys.argv", ["localhost_dashboard.py", "--watch"])
@patch("time.sleep", side_effect=KeyboardInterrupt)
@patch("builtins.print")
def test_main_watch_keyboard_interrupt(mock_print, mock_sleep, mock_get_servers):
    main()
    mock_get_servers.assert_called_once()
    mock_sleep.assert_called_once_with(3)

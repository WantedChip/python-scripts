"""Unit tests for Webhook Debugger."""

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Generator, Tuple
from unittest.mock import MagicMock, patch

# noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest  # noqa: E402
from webhook_debugger.main import (  # noqa: E402
    WebhookDatabase,
    WebhookServer,
    compare_requests,
    list_requests,
    main,
    replay_request,
    show_request,
)


@pytest.fixture(name="db")
def db_fixture(tmp_path: Path) -> Generator[WebhookDatabase, None, None]:
    """Provide a temporary SQLite database instance."""
    db_file = tmp_path / "test_webhook.db"
    db_inst = WebhookDatabase(str(db_file))
    yield db_inst
    db_inst.close()


def test_database_operations(db: WebhookDatabase) -> None:
    """Test standard database inserts and queries."""
    req_id = db.insert_request(
        method="POST",
        path="/webhook",
        headers={"Content-Type": "application/json", "X-Key": "val"},
        body='{"event": "test"}',
    )
    assert req_id == 1

    requests = db.get_requests()
    assert len(requests) == 1
    assert requests[0]["id"] == 1
    assert requests[0]["method"] == "POST"
    assert requests[0]["headers"]["X-Key"] == "val"
    assert requests[0]["body"] == '{"event": "test"}'

    r = db.get_request(1)
    assert r is not None
    assert r["id"] == 1

    assert db.get_request(999) is None


@pytest.fixture(name="running_server")
def running_server_fixture(
    db: WebhookDatabase,
) -> Generator[Tuple[str, int], None, None]:
    """Start Webhook Server in a background thread."""
    # Use port 0 to bind to any available random port
    server = WebhookServer(("127.0.0.1", 0), db)
    host, port = server.server_address

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield host, port

    server.shutdown()
    server.server_close()


def test_http_request_logging(
    running_server: Tuple[str, int], db: WebhookDatabase
) -> None:
    """Test server logs incoming HTTP operations in SQLite database."""
    host, port = running_server
    url = f"http://{host}:{port}/my/custom/path"

    # Send a POST request
    data = b"hello payload"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"X-Test-Header": "yes", "Content-Type": "text/plain"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        resp_data = json.loads(response.read().decode("utf-8"))
        assert resp_data["status"] == "ok"
        req_id = resp_data["request_id"]

    # Verify requests logged in SQLite
    logged_req = db.get_request(req_id)
    assert logged_req is not None
    assert logged_req["method"] == "POST"
    assert logged_req["path"] == "/my/custom/path"
    assert logged_req["headers"].get("X-Test-Header") == "yes"
    assert logged_req["body"] == "hello payload"


def test_list_requests(db: WebhookDatabase, capsys: pytest.CaptureFixture[str]) -> None:
    """Test listing recorded requests in table format."""
    # Empty db
    with patch("webhook_debugger.main.logger") as mock_logger:
        list_requests(db.db_path)
        mock_logger.info.assert_any_call(
            "No captured webhook requests found in database."
        )

    # Populate
    db.insert_request("GET", "/test", {"Accept": "*/*"}, "")
    list_requests(db.db_path)
    captured = capsys.readouterr()
    assert "GET" in captured.out
    assert "/test" in captured.out


def test_show_request(db: WebhookDatabase, capsys: pytest.CaptureFixture[str]) -> None:
    """Test showing detailed parameters for a recorded request ID."""
    db.insert_request("POST", "/json", {"Content-Type": "application/json"}, '{"a": 1}')
    show_request(db.db_path, 1)
    captured = capsys.readouterr()
    assert "Request ID: 1" in captured.out
    assert "Method    : POST" in captured.out
    assert "Content-Type: application/json" in captured.out
    # JSON body should be pretty-printed
    assert '"a": 1' in captured.out


def test_show_request_invalid(db: WebhookDatabase) -> None:
    """Test show_request fails on invalid request ID."""
    with pytest.raises(SystemExit) as excinfo:
        show_request(db.db_path, 999)
    assert excinfo.value.code == 1


def test_replay_request_success(db: WebhookDatabase) -> None:
    """Test replaying a captured request to an endpoint."""
    db.insert_request("POST", "/action", {"Content-Type": "text/plain"}, "payload")

    # Mock urllib urlopen response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"success response"

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        replay_request(db.db_path, 1, "http://mock-target.com/receiver")
        mock_urlopen.assert_called_once()
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        assert req.full_url == "http://mock-target.com/receiver"
        assert req.method == "POST"
        assert req.data == b"payload"
        assert req.headers.get("Content-type") == "text/plain"


def test_replay_request_http_error(db: WebhookDatabase) -> None:
    """Test replaying handles HTTP errors safely."""
    db.insert_request("POST", "/action", {}, "")

    mock_error = urllib.error.HTTPError(
        url="http://mock.com",
        code=500,
        msg="Internal Server Error",
        hdrs=MagicMock(),
        fp=MagicMock(),
    )
    mock_error.read = MagicMock(return_value=b"server crashed")

    with patch("urllib.request.urlopen", side_effect=mock_error):
        with pytest.raises(SystemExit) as excinfo:
            replay_request(db.db_path, 1, "http://mock.com")
        assert excinfo.value.code == 1


def test_replay_request_general_error(db: WebhookDatabase) -> None:
    """Test replaying handles general socket/network errors safely."""
    db.insert_request("POST", "/action", {}, "")

    with patch("urllib.request.urlopen", side_effect=Exception("network down")):
        with pytest.raises(SystemExit) as excinfo:
            replay_request(db.db_path, 1, "http://mock.com")
        assert excinfo.value.code == 1


def test_replay_request_invalid_id(db: WebhookDatabase) -> None:
    """Test replaying raises error on invalid ID."""
    with pytest.raises(SystemExit) as excinfo:
        replay_request(db.db_path, 999, "http://mock.com")
    assert excinfo.value.code == 1


def test_compare_requests_identical(
    db: WebhookDatabase, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test comparing identical requests reports no difference."""
    db.insert_request("POST", "/json", {"X-Key": "A"}, '{"a": 1}')
    db.insert_request("POST", "/json", {"X-Key": "A"}, '{"a": 1}')

    with patch("webhook_debugger.main.logger") as mock_logger:
        compare_requests(db.db_path, 1, 2)
        mock_logger.info.assert_any_call("Requests are completely identical.")


def test_compare_requests_different(
    db: WebhookDatabase, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test diff generator reports header/body changes."""
    db.insert_request("POST", "/json", {"X-Key": "A"}, '{"a": 1}')
    db.insert_request("POST", "/json", {"X-Key": "B"}, '{"a": 2}')

    compare_requests(db.db_path, 1, 2)
    captured = capsys.readouterr()
    assert "Unified Differences" in captured.out
    assert "-  X-Key: A" in captured.out
    assert "+  X-Key: B" in captured.out
    assert '-  "a": 1' in captured.out
    assert '+  "a": 2' in captured.out


def test_compare_requests_invalid(db: WebhookDatabase) -> None:
    """Test comparing raises error on missing ID."""
    db.insert_request("GET", "/ok", {}, "")

    with pytest.raises(SystemExit) as excinfo:
        compare_requests(db.db_path, 1, 999)
    assert excinfo.value.code == 1

    with pytest.raises(SystemExit) as excinfo:
        compare_requests(db.db_path, 999, 1)
    assert excinfo.value.code == 1


def test_cli_main_list(
    db: WebhookDatabase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI main list command routing."""
    db.insert_request("GET", "/ok", {}, "")

    args = [
        "webhook_debugger",
        "--db-path",
        db.db_path,
        "list",
    ]
    monkeypatch.setattr(sys, "argv", args)
    main()
    captured = capsys.readouterr()
    assert "GET" in captured.out
    assert "/ok" in captured.out


def test_cli_main_show(
    db: WebhookDatabase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI main show command routing."""
    db.insert_request("GET", "/ok", {}, "")

    args = [
        "webhook_debugger",
        "--db-path",
        db.db_path,
        "show",
        "1",
    ]
    monkeypatch.setattr(sys, "argv", args)
    main()
    captured = capsys.readouterr()
    assert "Method    : GET" in captured.out


def test_cli_main_replay(db: WebhookDatabase, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI main replay command routing."""
    db.insert_request("GET", "/ok", {}, "")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"ok"

    args = [
        "webhook_debugger",
        "--db-path",
        db.db_path,
        "replay",
        "1",
        "--to",
        "http://mock-target.com",
    ]
    monkeypatch.setattr(sys, "argv", args)

    with patch("urllib.request.urlopen", return_value=mock_response):
        main()


def test_cli_main_compare(
    db: WebhookDatabase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI main compare command routing."""
    db.insert_request("GET", "/ok", {}, "")
    db.insert_request("GET", "/no", {}, "")

    args = [
        "webhook_debugger",
        "--db-path",
        db.db_path,
        "compare",
        "1",
        "2",
    ]
    monkeypatch.setattr(sys, "argv", args)
    main()
    captured = capsys.readouterr()
    assert "Unified Differences" in captured.out


def test_cli_main_start_server(
    db: WebhookDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test CLI start server subcommand is intercepted and
    exits on KeyboardInterrupt."""
    args = [
        "webhook_debugger",
        "--db-path",
        db.db_path,
        "start",
        "--host",
        "127.0.0.1",
        "--port",
        "0",
    ]
    monkeypatch.setattr(sys, "argv", args)

    # Throw KeyboardInterrupt immediately inside serve_forever
    with patch(
        "webhook_debugger.main.WebhookServer.serve_forever",
        side_effect=KeyboardInterrupt,
    ):
        main()

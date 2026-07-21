"""Unit tests for the webhook-lab script."""

import hmac
import json
import logging
import os
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from unittest.mock import ANY, MagicMock, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/webhook-lab")

# pylint: disable=wrong-import-position
from webhook_lab import (  # noqa: E402
    WebhookDatabase,
    WebhookHTTPHandler,
    WebhookServer,
    compare_requests,
    list_requests,
    main,
    redact_json,
    redact_payload,
    replay_request,
    setup_logging,
    show_request,
    start_server,
    verify_signature,
)


@pytest.fixture
def temp_db() -> str:
    """Fixture supplying temporary SQLite DB path."""
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


def test_database_operations(temp_db: str) -> None:
    """Test standard database insert and retrieve operations."""
    db = WebhookDatabase(temp_db)
    headers = {"Content-Type": "application/json", "Authorization": "Bearer 123"}
    body = '{"foo": "bar"}'

    req_id = db.insert_request("POST", "/hook", headers, body, verified=1)
    assert req_id == 1

    requests = db.get_requests()
    assert len(requests) == 1
    assert requests[0]["method"] == "POST"
    assert requests[0]["path"] == "/hook"
    assert requests[0]["headers"] == headers
    assert requests[0]["body"] == body
    assert requests[0]["verified"] == 1

    req = db.get_request(1)
    assert req is not None
    assert req["id"] == 1

    assert db.get_request(99) is None
    db.close()


def test_database_insert_failure(temp_db: str):
    """Test database insert raising error if lastrowid is None."""
    db = WebhookDatabase(temp_db)
    mock_cursor = MagicMock()
    mock_cursor.lastrowid = None
    db.conn = MagicMock()
    db.conn.execute.return_value = mock_cursor
    with pytest.raises(
        sqlite3.DatabaseError, match="Failed to retrieve inserted row ID."
    ):
        db.insert_request("POST", "/hook", {}, "body", 1)
    db.close()


def test_verify_signature_raw_hmac() -> None:
    """Test signature verification with raw-hmac style."""
    body = b"hello world"
    secret = "secret"
    sig = hmac.new(secret.encode(), body, "sha256").hexdigest()

    headers = {"X-Signature": sig}
    assert verify_signature(body, headers, "X-Signature", secret, "raw-hmac") == 1
    assert verify_signature(body, headers, "X-Signature", "wrong", "raw-hmac") == 0
    assert verify_signature(body, {}, "X-Signature", secret, "raw-hmac") == 0


def test_verify_signature_github() -> None:
    """Test signature verification with github style."""
    body = b"hello world"
    secret = "secret"
    sig = "sha256=" + hmac.new(secret.encode(), body, "sha256").hexdigest()

    headers = {"X-Hub-Signature-256": sig}
    assert verify_signature(body, headers, "X-Hub-Signature-256", secret, "github") == 1


def test_verify_signature_stripe() -> None:
    """Test signature verification with stripe style."""
    body = b"hello world"
    secret = "secret"
    t = "123456"
    expected_payload = t.encode() + b"." + body
    sig = hmac.new(secret.encode(), expected_payload, "sha256").hexdigest()

    headers = {"Stripe-Signature": f"t={t},v1={sig}"}
    assert verify_signature(body, headers, "Stripe-Signature", secret, "stripe") == 1
    assert verify_signature(body, headers, "Stripe-Signature", "wrong", "stripe") == 0

    assert (
        verify_signature(
            body, {"Stripe-Signature": "t=123456"}, "Stripe-Signature", secret, "stripe"
        )
        == 0
    )


def test_verify_signature_unconfigured() -> None:
    """Test signature verification returns -1 if unconfigured."""
    assert verify_signature(b"body", {}, None, None, "raw-hmac") == -1


def test_verify_signature_exception():
    """Test verify_signature catches Exceptions gracefully and returns 0."""
    assert (
        verify_signature(
            None, {"X-Signature": "sig"}, "X-Signature", "secret", "raw-hmac"
        )
        == 0
    )


def test_secret_redaction() -> None:
    """Test case-insensitive header and JSON body key redaction."""
    headers = {"Authorization": "Bearer 123", "Content-Type": "application/json"}
    body = json.dumps(
        {"password": "secret_pass", "nested": {"token": "secret_token", "normal": 42}}
    )
    redact_keys = ["authorization", "password", "token"]

    red_headers, red_body = redact_payload(headers, body, redact_keys)
    assert red_headers["Authorization"] == "[REDACTED]"
    assert red_headers["Content-Type"] == "application/json"

    parsed_body = json.loads(red_body)
    assert parsed_body["password"] == "[REDACTED]"
    assert parsed_body["nested"]["token"] == "[REDACTED]"
    assert parsed_body["nested"]["normal"] == 42


def test_redact_json_non_dict() -> None:
    """Test redact_json on basic types and list of objects."""
    assert redact_json("string", ["key"]) == "string"
    assert redact_json([{"key": "val"}], ["key"]) == [{"key": "[REDACTED]"}]


def test_redact_payload_invalid_json():
    """Test redact_payload returns un-redacted body if body is not valid JSON."""
    headers = {"Content-Type": "text/plain"}
    body = "not a json string"
    red_headers, red_body = redact_payload(headers, body, ["Authorization"])
    assert red_headers == headers
    assert red_body == body


def test_setup_logging():
    """Test setup_logging sets correct levels."""
    log_obj = logging.getLogger("webhook_lab")
    orig_level = log_obj.level
    orig_handlers = list(log_obj.handlers)

    try:
        log_obj.handlers = []
        setup_logging(verbose=True)
        assert log_obj.level == logging.DEBUG
        assert len(log_obj.handlers) == 1

        log_obj.handlers = []
        setup_logging(verbose=False)
        assert log_obj.level == logging.INFO
    finally:
        log_obj.level = orig_level
        log_obj.handlers = orig_handlers


def test_handler_do_request_invalid_signature():
    """Test handler do_request responds with 401 when signature verification fails."""
    mock_handler = MagicMock()
    mock_handler.headers = {"Content-Length": "11", "X-Signature": "invalid"}
    mock_handler.rfile = MagicMock()
    mock_handler.rfile.read.return_value = b"hello world"
    mock_handler.command = "POST"
    mock_handler.path = "/webhook"
    mock_handler.client_address = ("127.0.0.1", 1234)

    mock_server = MagicMock()
    mock_server.sig_header = "X-Signature"
    mock_server.sig_secret = "secret"
    mock_server.sig_style = "raw-hmac"
    mock_handler.server = mock_server

    WebhookHTTPHandler.do_request(mock_handler)

    mock_handler.send_response.assert_called_once_with(401)
    mock_handler.wfile.write.assert_called_once()


def test_handler_do_request_valid_signature():
    """Test handler do_request logs and responds with 200 when signature is valid."""
    mock_handler = MagicMock()
    body = b"hello world"
    secret = "secret"
    sig = hmac.new(secret.encode(), body, "sha256").hexdigest()

    mock_handler.headers = {"Content-Length": str(len(body)), "X-Signature": sig}
    mock_handler.rfile = MagicMock()
    mock_handler.rfile.read.return_value = body
    mock_handler.command = "POST"
    mock_handler.path = "/webhook"
    mock_handler.client_address = ("127.0.0.1", 1234)

    mock_server = MagicMock()
    mock_server.db = MagicMock(spec=WebhookDatabase)
    mock_server.db.insert_request.return_value = 42
    mock_server.sig_header = "X-Signature"
    mock_server.sig_secret = secret
    mock_server.sig_style = "raw-hmac"
    mock_handler.server = mock_server

    WebhookHTTPHandler.do_request(mock_handler)

    mock_handler.send_response.assert_called_once_with(200)
    mock_server.db.insert_request.assert_called_once()


def test_handler_do_request_no_content_length():
    """Test handler do_request handles empty Content-Length correctly."""
    mock_handler = MagicMock()
    mock_handler.headers = {}
    mock_handler.rfile = MagicMock()
    mock_handler.command = "GET"
    mock_handler.path = "/webhook"
    mock_handler.client_address = ("127.0.0.1", 1234)

    mock_server = MagicMock()
    mock_server.db = MagicMock(spec=WebhookDatabase)
    mock_server.db.insert_request.return_value = 42
    mock_server.sig_header = None
    mock_server.sig_secret = None
    mock_server.sig_style = "raw-hmac"
    mock_handler.server = mock_server

    WebhookHTTPHandler.do_request(mock_handler)
    mock_handler.rfile.read.assert_not_called()
    mock_handler.send_response.assert_called_once_with(200)


def test_handler_do_request_read_oserror():
    """Test handler do_request logging when body read throws OSError."""
    mock_handler = MagicMock()
    mock_handler.headers = {"Content-Length": "10"}
    mock_handler.rfile = MagicMock()
    mock_handler.rfile.read.side_effect = OSError("Read error")
    mock_handler.command = "POST"
    mock_handler.path = "/webhook"
    mock_handler.client_address = ("127.0.0.1", 1234)

    mock_server = MagicMock()
    mock_server.db = MagicMock(spec=WebhookDatabase)
    mock_server.db.insert_request.return_value = 42
    mock_server.sig_header = None
    mock_server.sig_secret = None
    mock_server.sig_style = "raw-hmac"
    mock_handler.server = mock_server

    WebhookHTTPHandler.do_request(mock_handler)
    mock_handler.send_response.assert_called_once_with(200)


def test_handler_do_request_send_response_oserror():
    """Test handler do_request error handling when send_response throws OSError."""
    mock_handler = MagicMock()
    mock_handler.headers = {}
    mock_handler.rfile = MagicMock()
    mock_handler.command = "GET"
    mock_handler.path = "/webhook"
    mock_handler.client_address = ("127.0.0.1", 1234)

    mock_server = MagicMock()
    mock_server.db = MagicMock(spec=WebhookDatabase)
    mock_server.db.insert_request.return_value = 42
    mock_server.sig_header = None
    mock_server.sig_secret = None
    mock_server.sig_style = "raw-hmac"
    mock_handler.server = mock_server

    mock_handler.send_response.side_effect = OSError("Write error")

    WebhookHTTPHandler.do_request(mock_handler)


def test_handler_do_request_unauthorized_send_response_oserror():
    """Test handler do_request error handling when send_response throws OSError."""
    mock_handler = MagicMock()
    mock_handler.headers = {"Content-Length": "10", "X-Signature": "invalid"}
    mock_handler.rfile = MagicMock()
    mock_handler.rfile.read.return_value = b"body"
    mock_handler.command = "POST"
    mock_handler.path = "/webhook"
    mock_handler.client_address = ("127.0.0.1", 1234)

    mock_server = MagicMock()
    mock_server.sig_header = "X-Signature"
    mock_server.sig_secret = "secret"
    mock_server.sig_style = "raw-hmac"
    mock_handler.server = mock_server

    mock_handler.send_response.side_effect = OSError("Write error")

    WebhookHTTPHandler.do_request(mock_handler)


def test_handler_http_methods():
    """Test that individual HTTP verb handlers call do_request."""
    for method in ["do_GET", "do_POST", "do_PUT", "do_PATCH", "do_DELETE"]:
        mock_handler = MagicMock(spec=WebhookHTTPHandler)
        getattr(WebhookHTTPHandler, method)(mock_handler)
        mock_handler.do_request.assert_called_once()


def test_webhook_server_init():
    """Test WebhookServer constructor captures attributes."""
    db = MagicMock(spec=WebhookDatabase)
    server = WebhookServer(("127.0.0.1", 8080), db, "X-Signature", "secret", "raw-hmac")
    assert server.db == db
    assert server.sig_header == "X-Signature"
    assert server.sig_secret == "secret"
    assert server.sig_style == "raw-hmac"
    server.server_close()


@patch("webhook_lab.WebhookDatabase")
@patch("webhook_lab.WebhookServer")
def test_start_server(mock_server_class, mock_db_class):
    """Test start_server correctly initializes db, server, serves, and closes."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_server = MagicMock()
    mock_server_class.return_value = mock_server

    start_server("127.0.0.1", 8080, "test.db", "header", "secret", "raw-hmac")

    mock_db_class.assert_called_once_with("test.db")
    mock_server_class.assert_called_once_with(
        ("127.0.0.1", 8080), mock_db, "header", "secret", "raw-hmac"
    )
    mock_server.serve_forever.assert_called_once()
    mock_server.server_close.assert_called_once()
    mock_db.close.assert_called_once()


@patch("webhook_lab.WebhookDatabase")
@patch("webhook_lab.WebhookServer")
def test_start_server_keyboard_interrupt(mock_server_class, mock_db_class):
    """Test start_server handles KeyboardInterrupt correctly."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_server = MagicMock()
    mock_server_class.return_value = mock_server
    mock_server.serve_forever.side_effect = KeyboardInterrupt()

    start_server("127.0.0.1", 8080, "test.db", None, None, "raw-hmac")

    mock_server.serve_forever.assert_called_once()
    mock_server.server_close.assert_called_once()
    mock_db.close.assert_called_once()


@patch("webhook_lab.WebhookDatabase")
@patch("builtins.print")
def test_list_requests(mock_print, mock_db_class):
    """Test list_requests prints the request logs correctly."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_requests.return_value = [
        {
            "id": 1,
            "timestamp": "2026-07-19T22:53:24",
            "method": "POST",
            "path": "/short-path",
            "headers": {},
            "body": "body",
            "verified": 1,
        },
        {
            "id": 2,
            "timestamp": "2026-07-19T22:54:24",
            "method": "GET",
            "path": "/very-long-path-that-needs-truncation-to-see-if-it-works",
            "headers": {},
            "body": "body2",
            "verified": 0,
        },
        {
            "id": 3,
            "timestamp": "2026-07-19T22:55:24",
            "method": "PUT",
            "path": "/another-path",
            "headers": {},
            "body": "",
            "verified": -1,
        },
    ]

    list_requests("test.db")

    mock_db.get_requests.assert_called_once()
    mock_db.close.assert_called_once()
    mock_print.assert_any_call("-" * 80)

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("..." in line for line in printed_lines)
    assert any("N/A" in line for line in printed_lines)
    assert any("SUCCESS" in line for line in printed_lines)


@patch("webhook_lab.WebhookDatabase")
@patch("webhook_lab.logger")
def test_list_requests_empty(mock_logger, mock_db_class):
    """Test list_requests behavior when no requests are in the db."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_requests.return_value = []

    list_requests("test.db")
    mock_logger.info.assert_called_once_with(
        "No captured webhook requests found in database."
    )


@patch("webhook_lab.WebhookDatabase")
@patch("builtins.print")
def test_show_request_success(mock_print, mock_db_class):
    """Test show_request displays the details of a found request."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_request.return_value = {
        "id": 42,
        "timestamp": "2026-07-19",
        "method": "POST",
        "path": "/hook",
        "headers": {"Authorization": "Bearer token"},
        "body": '{"sensitive": "data"}',
        "verified": 1,
    }

    show_request("test.db", 42, ["Authorization", "sensitive"])

    mock_db.get_request.assert_called_once_with(42)
    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("[REDACTED]" in line for line in printed_lines)


@patch("webhook_lab.WebhookDatabase")
@patch("builtins.print")
def test_show_request_empty_body(mock_print, mock_db_class):
    """Test show_request display formatting when request body is empty."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_request.return_value = {
        "id": 42,
        "timestamp": "2026-07-19",
        "method": "POST",
        "path": "/hook",
        "headers": {},
        "body": "",
        "verified": 1,
    }

    show_request("test.db", 42, [])
    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("(Empty Body)" in line for line in printed_lines)


@patch("webhook_lab.WebhookDatabase")
def test_show_request_not_found(mock_db_class):
    """Test show_request exits when request id is not found."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_request.return_value = None

    with pytest.raises(SystemExit) as excinfo:
        show_request("test.db", 99, [])
    assert excinfo.value.code == 1


@patch("webhook_lab.WebhookDatabase")
@patch("urllib.request.urlopen")
def test_replay_request_success(mock_urlopen, mock_db_class):
    """Test replay_request successfully prepares request structure."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_request.return_value = {
        "id": 42,
        "timestamp": "2026-07-19",
        "method": "POST",
        "path": "/hook",
        "headers": {
            "Host": "localhost",
            "Content-Length": "100",
            "Authorization": "Bearer mytoken",
            "X-Custom": "value",
        },
        "body": '{"key": "value"}',
        "verified": 1,
    }

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"success response"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    replay_request("test.db", 42, "http://target.com/api", ["Authorization"])

    mock_urlopen.assert_called_once()
    req_arg = mock_urlopen.call_args[0][0]
    assert isinstance(req_arg, urllib.request.Request)
    assert req_arg.full_url == "http://target.com/api"
    assert req_arg.get_method() == "POST"

    headers = req_arg.headers
    assert "Host" not in headers
    assert "Content-length" not in headers
    assert headers["Authorization"] == "[REDACTED]"
    assert headers["X-custom"] == "value"


@patch("webhook_lab.WebhookDatabase")
@patch("urllib.request.urlopen")
def test_replay_request_http_error(mock_urlopen, mock_db_class):
    """Test replay_request exit behavior when target endpoint responds
    with HTTP Error."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_request.return_value = {
        "id": 42,
        "timestamp": "2026-07-19",
        "method": "POST",
        "path": "/hook",
        "headers": {},
        "body": '{"key": "value"}',
        "verified": 1,
    }

    fp = MagicMock()
    fp.read.return_value = b"error message"
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "http://target.com", 500, "Internal Server Error", {}, fp
    )

    with pytest.raises(SystemExit) as excinfo:
        replay_request("test.db", 42, "http://target.com", [])
    assert excinfo.value.code == 1


@patch("webhook_lab.WebhookDatabase")
@patch("urllib.request.urlopen")
def test_replay_request_generic_exception(mock_urlopen, mock_db_class):
    """Test replay_request exit behavior when urlopen throws exception."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_request.return_value = {
        "id": 42,
        "timestamp": "2026-07-19",
        "method": "POST",
        "path": "/hook",
        "headers": {},
        "body": '{"key": "value"}',
        "verified": 1,
    }

    mock_urlopen.side_effect = OSError("Connection refused")

    with pytest.raises(SystemExit) as excinfo:
        replay_request("test.db", 42, "http://target.com", [])
    assert excinfo.value.code == 1


@patch("webhook_lab.WebhookDatabase")
def test_replay_request_not_found(mock_db_class):
    """Test replay_request exit behavior when requested request ID is missing."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_request.return_value = None

    with pytest.raises(SystemExit) as excinfo:
        replay_request("test.db", 99, "http://target.com", [])
    assert excinfo.value.code == 1


@patch("webhook_lab.WebhookDatabase")
@patch("builtins.print")
def test_compare_requests_identical(mock_print, mock_db_class):
    """Test compare_requests logs output when requests are identical."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    req = {
        "id": 1,
        "timestamp": "2026-07-19",
        "method": "POST",
        "path": "/hook",
        "headers": {"Header": "value"},
        "body": "body_content",
        "verified": 1,
    }
    mock_db.get_request.side_effect = [req, req]

    compare_requests("test.db", 1, 2, [])

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert not any("Unified Differences" in line for line in printed_lines)


@patch("webhook_lab.WebhookDatabase")
@patch("builtins.print")
def test_compare_requests_different(mock_print, mock_db_class):
    """Test compare_requests displays diff correctly if request contents differ."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    req_a = {
        "id": 1,
        "timestamp": "2026-07-19",
        "method": "POST",
        "path": "/hook",
        "headers": {"Header": "valueA"},
        "body": "body_contentA",
        "verified": 1,
    }
    req_b = {
        "id": 2,
        "timestamp": "2026-07-19",
        "method": "POST",
        "path": "/hook",
        "headers": {"Header": "valueB"},
        "body": "body_contentB",
        "verified": 1,
    }
    mock_db.get_request.side_effect = [req_a, req_b]

    compare_requests("test.db", 1, 2, [])

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("Unified Differences" in line for line in printed_lines)


@patch("webhook_lab.WebhookDatabase")
def test_compare_requests_not_found(mock_db_class):
    """Test compare_requests handles exit code when request records are missing."""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db

    mock_db.get_request.side_effect = [None, None]
    with pytest.raises(SystemExit) as excinfo:
        compare_requests("test.db", 1, 2, [])
    assert excinfo.value.code == 1

    mock_db.get_request.side_effect = [{"id": 1}, None]
    with pytest.raises(SystemExit) as excinfo:
        compare_requests("test.db", 1, 2, [])
    assert excinfo.value.code == 1


@patch("webhook_lab.start_server")
def test_main_start_command(mock_start: MagicMock) -> None:
    """Test starting the server via main CLI entry."""
    with patch("sys.argv", ["webhook-lab", "start", "--port", "8888"]):
        main()
        mock_start.assert_called_once_with(
            "127.0.0.1", 8888, "webhook_lab.db", None, None, "raw-hmac"
        )


@patch("webhook_lab.list_requests")
def test_main_list_command(mock_list):
    """Test triggering list via main CLI command."""
    with patch("sys.argv", ["webhook-lab", "list"]):
        main()
        mock_list.assert_called_once()


@patch("webhook_lab.show_request")
def test_main_show_command(mock_show):
    """Test triggering show command with parameters."""
    with patch("sys.argv", ["webhook-lab", "show", "42"]):
        main()
        mock_show.assert_called_once_with("webhook_lab.db", 42, ANY)


@patch("webhook_lab.replay_request")
def test_main_replay_command(mock_replay):
    """Test triggering replay command with target URL argument."""
    with patch("sys.argv", ["webhook-lab", "replay", "42", "--to", "http://url"]):
        main()
        mock_replay.assert_called_once_with("webhook_lab.db", 42, "http://url", ANY)


@patch("webhook_lab.compare_requests")
def test_main_compare_command(mock_compare):
    """Test triggering compare command with two database IDs."""
    with patch("sys.argv", ["webhook-lab", "compare", "1", "2"]):
        main()
        mock_compare.assert_called_once_with("webhook_lab.db", 1, 2, ANY)

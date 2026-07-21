import json
import os
import sys
import urllib.error
import urllib.request
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add parent directory to sys.path so we can import the script
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from mock_from_traffic import (  # noqa: E402
    TrafficRecorderHandler,
    get_mock_filename,
    main,
    sanitize_dict,
    write_mock_driver,
)


class MockHandler(TrafficRecorderHandler):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_sanitize_dict():
    data = {
        "authorization": "Bearer token123",
        "nested": {"api_key": "secret_key", "normal_field": 42},
        "items": [
            {"password": "pass", "name": "user"},
            {"secret": "val", "value": "xyz"},
        ],
    }
    sanitize_keys = ["authorization", "api_key", "password", "secret"]
    sanitized = sanitize_dict(data, sanitize_keys)
    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["normal_field"] == 42
    assert sanitized["items"][0]["password"] == "[REDACTED]"
    assert sanitized["items"][0]["name"] == "user"
    assert sanitized["items"][1]["secret"] == "[REDACTED]"
    assert sanitized["items"][1]["value"] == "xyz"


def test_get_mock_filename():
    assert get_mock_filename("GET", "/", "") == "get_root.json"
    assert (
        get_mock_filename("POST", "/api/v1/users-list", "")
        == "post_api_v1_users_list.json"
    )

    fn1 = get_mock_filename("GET", "/api/data", "id=123")
    fn2 = get_mock_filename("GET", "/api/data", "id=124")
    assert fn1.startswith("get_api_data_")
    assert fn1.endswith(".json")
    assert fn1 != fn2


@patch("builtins.open", new_callable=mock_open)
def test_write_mock_driver_success(mock_file):
    write_mock_driver("/mock/dir")
    mock_file.assert_called_once_with(
        os.path.join("/mock/dir", "mock_driver.py"), "w", encoding="utf-8"
    )


def test_handler_do_request_success():
    rfile_mock = MagicMock()
    rfile_mock.read.return_value = b'{"input": "data"}'

    wfile_mock = MagicMock()

    headers_mock = MagicMock()
    headers_mock.get.side_effect = lambda key, default=None: (
        "21" if key == "Content-Length" else default
    )
    headers_mock.items.return_value = [
        ("Host", "localhost:8080"),
        ("Content-Type", "application/json"),
    ]

    handler = MockHandler(
        command="POST",
        path="/api/v1/test?query=val",
        rfile=rfile_mock,
        wfile=wfile_mock,
        headers=headers_mock,
        target_url="https://api.example.com",
        output_dir="/mock/output",
        sanitize_keys=["auth"],
        verbose=True,
    )

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.getheaders.return_value = [
        ("Content-Type", "application/json"),
        ("X-Test", "123"),
    ]
    mock_resp.read.return_value = b'{"response": "ok"}'

    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.record_traffic = MagicMock()

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        handler.do_request()

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://api.example.com/api/v1/test?query=val"
        assert req.data == b'{"input": "data"}'
        assert req.method == "POST"
        assert req.headers["Host"] == "api.example.com"
        assert req.headers["Content-type"] == "application/json"

        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_called_with("X-Test", "123")
        handler.end_headers.assert_called_once()
        wfile_mock.write.assert_called_once_with(b'{"response": "ok"}')

        handler.record_traffic.assert_called_once_with(
            "/api/v1/test?query=val",
            b'{"input": "data"}',
            200,
            [("Content-Type", "application/json"), ("X-Test", "123")],
            b'{"response": "ok"}',
        )


def test_handler_do_request_http_error():
    rfile_mock = MagicMock()
    wfile_mock = MagicMock()
    headers_mock = MagicMock()
    headers_mock.get.return_value = "0"
    headers_mock.items.return_value = []

    handler = MockHandler(
        command="GET",
        path="/error-path",
        rfile=rfile_mock,
        wfile=wfile_mock,
        headers=headers_mock,
        target_url="https://api.example.com",
        output_dir="/mock/output",
        sanitize_keys=[],
        verbose=False,
    )

    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.record_traffic = MagicMock()

    err = urllib.error.HTTPError(
        "https://api.example.com/error-path",
        400,
        "Bad Request",
        MagicMock(),
        MagicMock(),
    )
    err.read = MagicMock(return_value=b"error body")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = err

        handler.do_request()

        handler.send_response.assert_called_once_with(400)
        wfile_mock.write.assert_called_once_with(b"error body")
        handler.record_traffic.assert_called_once()


def test_handler_do_request_generic_error():
    rfile_mock = MagicMock()
    wfile_mock = MagicMock()
    headers_mock = MagicMock()
    headers_mock.get.return_value = "0"
    headers_mock.items.return_value = []

    handler = MockHandler(
        command="GET",
        path="/error-path",
        rfile=rfile_mock,
        wfile=wfile_mock,
        headers=headers_mock,
        target_url="https://api.example.com",
        output_dir="/mock/output",
        sanitize_keys=[],
        verbose=False,
    )

    handler.send_response = MagicMock()
    handler.end_headers = MagicMock()

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = OSError("Connection timed out")

        handler.do_request()

        handler.send_response.assert_called_once_with(502)
        handler.end_headers.assert_called_once()
        wfile_mock.write.assert_called_once()
        assert b"Connection timed out" in wfile_mock.write.call_args[0][0]


@patch("builtins.open", new_callable=mock_open)
@patch("mock_from_traffic.get_mock_filename", return_value="get_test.json")
def test_record_traffic(mock_filename, mock_file):
    headers_mock = MagicMock()
    headers_mock.items.return_value = [
        ("Authorization", "secret-token"),
        ("Content-Type", "application/json"),
    ]

    handler = MockHandler(
        command="GET",
        headers=headers_mock,
        output_dir="/mock/output",
        sanitize_keys=["authorization", "auth", "set-cookie"],
    )

    req_body = b'{"auth": "123", "data": "yes"}'
    resp_headers = [("Content-Type", "application/json"), ("Set-Cookie", "session-id")]
    resp_body = b'{"result": "success"}'

    handler.record_traffic(
        "/api/test?query=abc", req_body, 200, resp_headers, resp_body
    )

    mock_file.assert_called_once_with(
        os.path.join("/mock/output", "get_test.json"), "w", encoding="utf-8"
    )

    written_data = "".join(call[0][0] for call in mock_file().write.call_args_list)
    record = json.loads(written_data)

    assert record["request"]["method"] == "GET"
    assert record["request"]["path"] == "/api/test"
    assert record["request"]["query"] == "query=abc"
    assert record["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert record["request"]["body"]["auth"] == "[REDACTED]"
    assert record["request"]["body"]["data"] == "yes"

    assert record["response"]["status_code"] == 200
    assert record["response"]["headers"]["Set-Cookie"] == "[REDACTED]"
    assert record["response"]["body"]["result"] == "success"


@patch("builtins.open", new_callable=mock_open)
def test_record_traffic_invalid_json(mock_file):
    headers_mock = MagicMock()
    headers_mock.items.return_value = []

    handler = MockHandler(
        command="POST",
        headers=headers_mock,
        output_dir="/mock/output",
        sanitize_keys=[],
    )

    req_body = b"invalid json data \xff"
    resp_body = b"another non-json \xfe"

    handler.record_traffic("/api/binary", req_body, 200, [], resp_body)

    written_data = "".join(call[0][0] for call in mock_file().write.call_args_list)
    record = json.loads(written_data)

    assert "invalid json data" in record["request"]["body"]
    assert "another non-json" in record["response"]["body"]


def test_http_methods():
    handler = MockHandler()
    handler.do_request = MagicMock()

    handler.do_GET()
    handler.do_POST()
    handler.do_PUT()
    handler.do_DELETE()
    handler.do_PATCH()
    handler.do_OPTIONS()
    handler.do_HEAD()

    assert handler.do_request.call_count == 7


@patch(
    "sys.argv",
    [
        "mock_from_traffic.py",
        "-t",
        "api.github.com",
        "-p",
        "9090",
        "-o",
        "custom_mocks",
    ],
)
@patch("os.makedirs")
@patch("mock_from_traffic.write_mock_driver")
@patch("mock_from_traffic.ThreadingHTTPServer")
@patch("builtins.print")
def test_main_success(mock_print, mock_server, mock_write_driver, mock_makedirs):
    mock_server_instance = MagicMock()
    mock_server.return_value = mock_server_instance

    main()

    mock_makedirs.assert_called_once_with("custom_mocks", exist_ok=True)
    mock_write_driver.assert_called_once_with("custom_mocks")

    assert mock_server.call_args[0][0] == ("localhost", 9090)
    handler_class = mock_server.call_args[0][1]
    assert handler_class.target_url == "https://api.github.com"
    assert handler_class.output_dir == "custom_mocks"
    assert "Authorization" in handler_class.sanitize_keys
    mock_server_instance.serve_forever.assert_called_once()


@patch("sys.argv", ["mock_from_traffic.py", "-t", "api.github.com"])
@patch("os.makedirs")
@patch("mock_from_traffic.write_mock_driver")
@patch("mock_from_traffic.ThreadingHTTPServer")
@patch("sys.exit")
@patch("builtins.print")
def test_main_keyboard_interrupt(
    mock_print, mock_exit, mock_server, mock_write_driver, mock_makedirs
):
    mock_server_instance = MagicMock()
    mock_server_instance.serve_forever.side_effect = KeyboardInterrupt
    mock_server.return_value = mock_server_instance
    mock_exit.side_effect = SystemExit

    with pytest.raises(SystemExit):
        main()

    mock_exit.assert_called_once_with(0)

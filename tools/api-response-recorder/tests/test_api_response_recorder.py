"""Unit tests for API Response Recorder."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

# noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest  # noqa: E402
from api_response_recorder.main import (  # noqa: E402
    fetch_api,
    generate_fixture_loader,
    main,
    record_endpoint,
    sanitize_body,
    sanitize_headers,
    sanitize_json_val,
)


def test_sanitize_headers() -> None:
    """Test sensitive HTTP headers are masked."""
    headers = {
        "Authorization": "Bearer secret_token_123",
        "Content-Type": "application/json",
        "Cookie": "sess_id=xyz",
        "X-Custom": "val",
    }
    sanitized = sanitize_headers(headers, custom_headers={"x-custom"})
    assert sanitized["Authorization"] == "<MASKED>"
    assert sanitized["Cookie"] == "<MASKED>"
    assert sanitized["X-Custom"] == "<MASKED>"
    assert sanitized["Content-Type"] == "application/json"


def test_sanitize_json_val() -> None:
    """Test sensitive JSON keys and regex patterns are masked recursively."""
    data = {
        "user": {
            "name": "Octocat",
            "password": "my_password_123",
            "secret_token": "token_val",
        },
        "emails": ["user@github.com", "backup@github.com"],
        "keys": [{"type": "ssh", "key": "ssh-rsa aaa"}],
        "non_sensitive": 42,
    }

    # Mask key patterns
    mask_keys = {"password", "key", "secret_token"}
    custom_patterns = [r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"]  # email regex

    sanitized = sanitize_json_val(data, mask_keys, custom_patterns)
    assert sanitized["user"]["name"] == "Octocat"
    assert sanitized["user"]["password"] == "<MASKED>"
    assert sanitized["user"]["secret_token"] == "<MASKED>"
    assert sanitized["emails"] == ["<MASKED>", "<MASKED>"]
    assert sanitized["keys"][0]["key"] == "<MASKED>"
    assert sanitized["non_sensitive"] == 42


def test_sanitize_body_text() -> None:
    """Test text body sanitization falls back to regex matching."""
    body = "Server key: 12345, Admin email: admin@test.com"
    pat = [r"admin@test\.com"]
    res = sanitize_body(body, set(), pat)
    assert "admin@test.com" not in res
    assert "<MASKED>" in res

    # Empty body
    assert sanitize_body("", set(), []) == ""


def test_fetch_api_success() -> None:
    """Test fetch_api executes request and returns headers and body."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers.items.return_value = [("Content-Type", "application/json")]
    mock_resp.read.return_value = b'{"ok": true}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        status, headers, body = fetch_api(
            url="http://api.test/get",
            method="POST",
            headers={"Content-Type": "application/json", "Content-Length": "12"},
            data="{}",
        )
        mock_urlopen.assert_called_once()
        assert status == 200
        assert headers["Content-Type"] == "application/json"
        assert body == '{"ok": true}'


def test_fetch_api_http_error() -> None:
    """Test fetch_api captures and returns HTTP error status and body."""
    mock_error = urllib.error.HTTPError(
        url="http://api.test/error",
        code=404,
        msg="Not Found",
        hdrs=MagicMock(),
        fp=MagicMock(),
    )
    mock_error.headers = {"X-Error": "yes"}
    mock_error.read = MagicMock(return_value=b"not found body")

    with patch("urllib.request.urlopen", side_effect=mock_error):
        status, headers, body = fetch_api("http://api.test/error", "GET", {}, None)
        assert status == 404
        assert headers["X-Error"] == "yes"
        assert body == "not found body"


def test_fetch_api_general_error() -> None:
    """Test fetch_api raises system exit on general socket exceptions."""
    with patch("urllib.request.urlopen", side_effect=Exception("connection closed")):
        with pytest.raises(SystemExit) as excinfo:
            fetch_api("http://api.test/error", "GET", {}, None)
        assert excinfo.value.code == 1


def test_generate_fixture_loader(tmp_path: Path) -> None:
    """Test generating pytest fixture loader helper code."""
    json_path = tmp_path / "user.json"
    py_path = tmp_path / "mock_user.py"

    generate_fixture_loader(json_path, py_path, "user_fixture")

    assert py_path.exists()
    code = py_path.read_text(encoding="utf-8")
    assert "def mock_user_fixture" in code
    assert 'fixture_file = Path(__file__).parent / "user.json"' in code


def test_record_endpoint(tmp_path: Path) -> None:
    """Test record_endpoint writes expected JSON and Python loader files."""
    json_path = tmp_path / "fixtures" / "octocat.json"
    py_path = tmp_path / "fixtures" / "mock_octocat.py"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers.items.return_value = [("Content-Type", "application/json")]
    mock_resp.read.return_value = b'{"login": "octocat", "password": "123"}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        record_endpoint(
            url="http://api.github.com/users/octocat",
            method="GET",
            headers={},
            data=None,
            output_json_path=json_path,
            output_py_path=py_path,
            mask_keys={"password"},
            mask_headers=set(),
            custom_patterns=[],
        )

    # Verify JSON saved and masked
    assert json_path.exists()
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["status"] == 200
        body = json.loads(data["body"])
        assert body["login"] == "octocat"
        assert body["password"] == "<MASKED>"

    # Verify PY loader written
    assert py_path.exists()
    code = py_path.read_text(encoding="utf-8")
    assert "def mock_octocat" in code


def test_cli_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI main routing parses args and executes recording."""
    json_path = tmp_path / "user.json"
    py_path = tmp_path / "mock_user.py"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers.items.return_value = []
    mock_resp.read.return_value = b"{}"
    mock_resp.__enter__.return_value = mock_resp

    args = [
        "api_response_recorder",
        "http://api.com/users",
        "--output-json",
        str(json_path),
        "--output-py",
        str(py_path),
        "--header",
        "Authorization: Token secret_123",
        "--mask-key",
        "token",
        "--mask-header",
        "custom-auth",
        "--mask-pattern",
        r"\d+",
    ]
    monkeypatch.setattr(sys, "argv", args)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        main()

    assert json_path.exists()
    assert py_path.exists()


def test_cli_main_invalid_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI main exits on invalid header format."""
    args = [
        "api_response_recorder",
        "http://api.com",
        "--output-json",
        "ok.json",
        "--header",
        "InvalidHeaderFormat",  # missing colon
    ]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1

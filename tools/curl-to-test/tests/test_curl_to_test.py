import os
import sys
from io import StringIO
from unittest.mock import patch

# Add parent directory to sys.path to import curl_to_test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import curl_to_test  # noqa: E402


def test_parse_curl_simple_get():
    cmd = "curl http://example.com"
    method, url, headers, data, data_type = curl_to_test.parse_curl(cmd)
    assert method == "GET"
    assert url == "http://example.com"
    assert headers == {}
    assert data == ""
    assert data_type == "data"


def test_parse_curl_explicit_post():
    cmd = "curl -X POST https://example.com/api"
    method, url, headers, data, data_type = curl_to_test.parse_curl(cmd)
    assert method == "POST"
    assert url == "https://example.com/api"
    assert headers == {}
    assert data == ""


def test_parse_curl_headers_and_data_raw():
    cmd = (
        "curl -X PUT https://api.com/v1/update \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        "  -H 'Authorization: Bearer token123' \\\n"
        '  --data-raw \'{"name":"john"}\''
    )
    method, url, headers, data, data_type = curl_to_test.parse_curl(cmd)
    assert method == "PUT"
    assert url == "https://api.com/v1/update"
    assert headers == {
        "Content-Type": "application/json",
        "Authorization": "Bearer token123",
    }
    assert data == {"name": "john"}
    assert data_type == "data-raw"


def test_parse_curl_data_without_method():
    cmd = "curl https://api.com/post -d 'foo=bar' -d 'baz=qux'"
    method, url, headers, data, data_type = curl_to_test.parse_curl(cmd)
    assert method == "POST"
    assert url == "https://api.com/post"
    assert data == "foo=bar&baz=qux"


def test_parse_curl_invalid_empty():
    try:
        curl_to_test.parse_curl("")
    except ValueError:
        pass


def test_generate_python_requests():
    headers = {"Authorization": "Bearer token"}
    data = {"foo": "bar"}
    code = curl_to_test.generate_python_requests(
        "POST", "https://api.com", headers, data
    )
    assert "requests.post" in code
    assert "json_data = {" in code
    assert "headers = {" in code
    assert "Authorization" in code

    code_text = curl_to_test.generate_python_requests(
        "PUT", "https://api.com", {}, "plain text data"
    )
    assert "requests.put" in code_text
    assert "data = 'plain text data'" in code_text


def test_generate_pytest_test():
    headers = {"Content-Type": "application/json"}
    data = {"foo": "bar"}
    code = curl_to_test.generate_pytest_test("POST", "https://api.com", headers, data)
    assert "def test_api_endpoint(requests_mock):" in code
    assert "requests_mock.register_uri(" in code
    assert "requests.post" in code


def test_generate_mock_fixture():
    code = curl_to_test.generate_mock_fixture("GET", "https://api.com", {}, None)
    assert "@pytest.fixture" in code
    assert "def mock_api_call" in code
    assert "GET" in code


def test_generate_api_doc():
    headers = {"Accept": "application/json"}
    data = {"hello": "world"}
    doc = curl_to_test.generate_api_doc("POST", "https://api.com/greet", headers, data)
    assert "### Endpoint: `/greet`" in doc
    assert "**Method:** `POST`" in doc
    assert "```json" in doc
    assert "hello" in doc


def test_main_missing_input():
    with patch("sys.argv", ["curl_to_test.py"]), patch(
        "sys.stdin.isatty", return_value=True
    ):
        try:
            curl_to_test.main()
        except SystemExit as excinfo:
            assert excinfo.code == 1


def test_main_parse_error():
    with patch("sys.argv", ["curl_to_test.py", "   "]), patch(
        "sys.stdin.isatty", return_value=True
    ):
        try:
            curl_to_test.main()
        except SystemExit as excinfo:
            assert excinfo.code == 1


def test_main_file_input(tmp_path):
    cmd_file = tmp_path / "curl.txt"
    cmd_file.write_text("curl http://example.com")

    with patch("sys.argv", ["curl_to_test.py", "--file", str(cmd_file)]):
        new_stdout = StringIO()
        with patch("sys.stdout", new_stdout):
            curl_to_test.main()

        output = new_stdout.getvalue()
        assert "PYTHON REQUESTS EXAMPLE" in output
        assert "PYTEST TEST CASE" in output
        assert "MOCK FIXTURE" in output
        assert "API DOCUMENTATION SNIPPET" in output


def test_main_output_file(tmp_path):
    out_file = tmp_path / "output.txt"
    with patch(
        "sys.argv",
        ["curl_to_test.py", "curl http://example.com", "--output", str(out_file)],
    ):
        curl_to_test.main()

    assert out_file.exists()
    content = out_file.read_text()
    assert "PYTHON REQUESTS EXAMPLE" in content

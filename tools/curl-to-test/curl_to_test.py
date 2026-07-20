#!/usr/bin/env python3
"""Convert a cURL command into Python requests code, pytest mock tests,

requests-mock fixtures, and API documentation snippets.
"""

import argparse
import json
import shlex
import sys
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def parse_curl(curl_cmd: str) -> Tuple[str, str, Dict[str, str], Any, str]:
    """Parse cURL command and extract method, url, headers, data, and data_type."""
    # Clean up multi-line backslashes
    curl_cmd = curl_cmd.replace("\\\n", " ").replace("\\\r\n", " ")

    try:
        tokens = shlex.split(curl_cmd)
    except ValueError:
        # Fallback to simple split if shlex fails due to quoting mismatch
        tokens = curl_cmd.split()

    if not tokens:
        raise ValueError("Empty command provided")

    # Verify command starts with curl
    if tokens[0].lower() != "curl" and "curl" in [t.lower() for t in tokens]:
        curl_idx = [t.lower() for t in tokens].index("curl")
        tokens = tokens[curl_idx:]

    method = "GET"
    url = ""
    headers: Dict[str, str] = {}
    data: List[str] = []
    data_type = "data"

    i = 1
    while i < len(tokens):
        token = tokens[i]

        # Method options
        if token in ("-X", "--request"):
            if i + 1 < len(tokens):
                method = tokens[i + 1].upper()
                i += 2
            else:
                i += 1
        # Header options
        elif token in ("-H", "--header"):
            if i + 1 < len(tokens):
                header_val = tokens[i + 1]
                if ":" in header_val:
                    key, val = header_val.split(":", 1)
                    headers[key.strip()] = val.strip()
                i += 2
            else:
                i += 1
        # Data options
        elif token in (
            "-d",
            "--data",
            "--data-raw",
            "--data-binary",
            "--data-urlencode",
        ):
            if i + 1 < len(tokens):
                data.append(tokens[i + 1])
                if method == "GET":
                    method = "POST"
                if token == "--data-raw":  # nosec B105
                    data_type = "data-raw"
                elif token == "--data-binary":  # nosec B105
                    data_type = "data-binary"
                elif token == "--data-urlencode":  # nosec B105
                    data_type = "data-urlencode"
                i += 2
            else:
                i += 1
        elif token.startswith("-"):
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                if token in (
                    "-v",
                    "--verbose",
                    "-s",
                    "--silent",
                    "-L",
                    "--location",
                    "-k",
                    "--insecure",
                ):
                    i += 1
                else:
                    i += 2
            else:
                i += 1
        else:
            if not url:
                url = token
            i += 1

    url = url.strip("'\"")

    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url

    combined_data: Any = ""
    if data:
        combined_data = "&".join(data)
        content_type = next(
            (v for k, v in headers.items() if k.lower() == "content-type"), ""
        )
        if "application/json" in content_type.lower():
            try:
                combined_data = json.loads(combined_data)
            except json.JSONDecodeError:
                pass

    return method, url, headers, combined_data, data_type


def generate_python_requests(
    method: str, url: str, headers: Dict[str, str], data: Any
) -> str:
    """Generate Python requests script snippet."""
    lines = [
        "import requests",
        "",
        f"url = {repr(url)}",
        "",
    ]

    if headers:
        lines.append("headers = {")
        for k, v in headers.items():
            lines.append(f"    {repr(k)}: {repr(v)},")
        lines.append("}")
        lines.append("")
    else:
        lines.append("headers = {}")
        lines.append("")

    if isinstance(data, dict):
        lines.append(f"json_data = {json.dumps(data, indent=4)}")
        lines.append("")
        lines.append(f"response = requests.{method.lower()}(")
        lines.append("    url,")
        lines.append("    headers=headers,")
        lines.append("    json=json_data,")
        lines.append(")")
    elif data:
        lines.append(f"data = {repr(data)}")
        lines.append("")
        lines.append(f"response = requests.{method.lower()}(")
        lines.append("    url,")
        lines.append("    headers=headers,")
        lines.append("    data=data,")
        lines.append(")")
    else:
        lines.append(f"response = requests.{method.lower()}(")
        lines.append("    url,")
        lines.append("    headers=headers,")
        lines.append(")")

    lines.append("")
    lines.append("print(f'Status Code: {response.status_code}')")
    lines.append("print(response.text)")

    return "\n".join(lines)


def generate_pytest_test(
    method: str, url: str, headers: Dict[str, str], data: Any
) -> str:
    """Generate pytest test function utilizing requests-mock."""
    lines = [
        "import pytest",
        "import requests",
        "",
        "def test_api_endpoint(requests_mock):",
        "    # Mock the API response",
        "    requests_mock.register_uri(",
        f"        {repr(method)},",
        f"        {repr(url)},",
        "        json={'status': 'success', 'data': 'mocked_response'},",
        "        status_code=200,",
        "    )",
        "",
        "    # Make the call",
        f"    url = {repr(url)}",
    ]

    if headers:
        lines.append("    headers = {")
        for k, v in headers.items():
            lines.append(f"        {repr(k)}: {repr(v)},")
        lines.append("    }")
    else:
        lines.append("    headers = {}")

    if isinstance(data, dict):
        lines.append(f"    json_data = {json.dumps(data)}")
        req_line = (
            f"    response = requests.{method.lower()}"
            "(url, headers=headers, json=json_data)"
        )
        lines.append(req_line)
    elif data:
        lines.append(f"    data = {repr(data)}")
        req_line = (
            f"    response = requests.{method.lower()}"
            "(url, headers=headers, data=data)"
        )
        lines.append(req_line)
    else:
        lines.append(f"    response = requests.{method.lower()}(url, headers=headers)")

    lines.append("")
    lines.append("    # Assertions")
    lines.append("    assert response.status_code == 200")
    lines.append(
        "    assert response.json() == {'status': 'success', 'data': 'mocked_response'}"
    )

    return "\n".join(lines)


# pylint: disable=unused-argument
def generate_mock_fixture(
    method: str, url: str, headers: Dict[str, str], data: Any
) -> str:
    """Generate pytest mock fixture block."""
    lines = [
        "import pytest",
        "",
        "@pytest.fixture",
        "def mock_api_call(requests_mock):",
        '    """Fixture to mock the API request."""',
        "    return requests_mock.register_uri(",
        f"        {repr(method)},",
        f"        {repr(url)},",
        "        json={'status': 'success', 'data': 'mocked_response'},",
        "        status_code=200,",
        "    )",
    ]
    return "\n".join(lines)


def generate_api_doc(method: str, url: str, headers: Dict[str, str], data: Any) -> str:
    """Generate Markdown API documentation snippet."""
    parsed_url = urlparse(url)
    endpoint_name = parsed_url.path if parsed_url.path else "/"

    lines = [
        f"### Endpoint: `{endpoint_name}`",
        "",
        f"- **Method:** `{method}`",
        f"- **URL:** `{url}`",
    ]

    if headers:
        lines.append("- **Headers:**")
        for k, v in headers.items():
            lines.append(f"  - `{k}: {v}`")

    if data:
        lines.append("")
        lines.append("**Request Body:**")
        lines.append("```json" if isinstance(data, dict) else "```text")
        if isinstance(data, dict):
            lines.append(json.dumps(data, indent=2))
        else:
            lines.append(str(data))
        lines.append("```")

    lines.append("")
    lines.append("**Response (200 OK Example):**")
    lines.append("```json")
    lines.append(json.dumps({"status": "success", "data": {}}, indent=2))
    lines.append("```")

    return "\n".join(lines)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert a cURL command into Python requests, pytest tests, "
            "mock fixtures, and API documentation."
        )
    )
    parser.add_argument(
        "curl_command",
        nargs="?",
        help="The raw cURL command string.",
    )
    parser.add_argument(
        "-f", "--file", help="Path to a file containing the cURL command."
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional path to output file.",
    )

    args = parser.parse_args()

    curl_input = ""
    if args.curl_command:
        curl_input = args.curl_command
    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                curl_input = f.read()
        except OSError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        if not sys.stdin.isatty():
            curl_input = sys.stdin.read()

    curl_input = curl_input.strip()
    if not curl_input:
        parser.print_help()
        sys.exit(1)

    try:
        method, url, headers, data, _ = parse_curl(curl_input)
    except (ValueError, OSError) as e:
        print(f"Error parsing cURL command: {e}", file=sys.stderr)
        sys.exit(1)

    requests_code = generate_python_requests(method, url, headers, data)
    pytest_test = generate_pytest_test(method, url, headers, data)
    mock_fixture = generate_mock_fixture(method, url, headers, data)
    api_doc = generate_api_doc(method, url, headers, data)

    output_lines = [
        "========================================================================",
        "1. PYTHON REQUESTS EXAMPLE",
        "========================================================================",
        requests_code,
        "",
        "========================================================================",
        "2. PYTEST TEST CASE",
        "========================================================================",
        pytest_test,
        "",
        "========================================================================",
        "3. MOCK FIXTURE",
        "========================================================================",
        mock_fixture,
        "",
        "========================================================================",
        "4. API DOCUMENTATION SNIPPET",
        "========================================================================",
        api_doc,
        "",
    ]
    output_text = "\n".join(output_lines)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_text)
            print(f"Successfully wrote output to {args.output}")
        except OSError as e:
            print(f"Error writing to output file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(output_text)


if __name__ == "__main__":
    main()

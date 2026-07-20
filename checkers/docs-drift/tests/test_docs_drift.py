import os
import sys
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

# Add import injection to resolve docs_drift
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import docs_drift  # noqa: E402


def test_gather_codebase_words_success():
    mock_walk = [
        ("/src", ["subdir"], ["app.py", "ignored.txt"]),
        ("/src/subdir", [], ["utils.js", "config.json"]),
    ]

    file_contents = {
        "/src/app.py": "def my_func():\n    return 'hello_world'",
        "/src/subdir/utils.js": "const val = 123;",
        "/src/subdir/config.json": '{"API_KEY": "secret"}',
    }

    def mock_open_side_effect(filepath, *args, **kwargs):
        normalized = filepath.replace(os.sep, "/")
        for path, content in file_contents.items():
            if normalized.endswith(path):
                return mock_open(read_data=content)()
        raise OSError()

    with patch("os.walk", return_value=mock_walk), patch(
        "builtins.open", side_effect=mock_open_side_effect
    ):
        words = docs_drift.gather_codebase_words("/src")
        assert "my_func" in words
        assert "hello_world" in words
        assert "val" in words
        assert "API_KEY" in words
        assert "secret" in words
        assert "ignored" not in words


def test_gather_codebase_words_oserror():
    mock_walk = [("/src", [], ["app.py"])]
    with patch("os.walk", return_value=mock_walk), patch(
        "builtins.open", side_effect=OSError
    ):
        words = docs_drift.gather_codebase_words("/src")
        assert words == set()


def test_check_docs_drift():
    mock_walk = [("/docs", [], ["readme.md"])]
    readme_content = """
    # Readme
    Check out [Valid Link](existing.py) and [Broken Link](missing.py).
    Also [Web](https://google.com) and [Mail](mailto:test@example.com).
    API is `MY_VALID_API` or maybe `MY_STALE_API`.
    Ignore `abc`, `1234`, and `some/path`.
    """

    def mock_exists(path):
        normalized = path.replace(os.sep, "/")
        return (
            normalized.endswith("existing.py")
            or normalized.endswith("readme.md")
            or normalized == "/docs"
        )

    code_words = {"MY_VALID_API", "other_word"}

    with patch("os.walk", return_value=mock_walk), patch(
        "builtins.open", mock_open(read_data=readme_content)
    ), patch("os.path.exists", side_effect=mock_exists):

        drifts = docs_drift.check_docs_drift("/docs", code_words)

        assert len(drifts) == 2

        # Check broken link
        broken_link = [d for d in drifts if d["type"] == "Broken Link / Path"][0]
        assert broken_link["reference"] == "missing.py"
        assert broken_link["line"] == 3

        # Check stale code ref
        stale_ref = [d for d in drifts if d["type"] == "Stale Code Reference"][0]
        assert stale_ref["reference"] == "MY_STALE_API"
        assert stale_ref["line"] == 5


def test_check_docs_drift_oserror():
    mock_walk = [("/docs", [], ["readme.md"])]
    with patch("os.walk", return_value=mock_walk), patch(
        "builtins.open", side_effect=OSError
    ):
        drifts = docs_drift.check_docs_drift("/docs", set())
        assert drifts == []


@patch("sys.argv", ["docs_drift.py", "--docs", "/docs", "--src", "/src"])
@patch("docs_drift.gather_codebase_words", return_value={"API_KEY"})
@patch("docs_drift.check_docs_drift", return_value=[])
def test_main_no_drift(mock_check, mock_gather):
    with patch("sys.stdout"), pytest.raises(SystemExit) as exc_info:
        docs_drift.main()
    assert exc_info.value.code == 0


@patch("sys.argv", ["docs_drift.py", "--docs", "/docs", "--src", "/src"])
@patch("docs_drift.gather_codebase_words", return_value={"API_KEY"})
@patch(
    "docs_drift.check_docs_drift",
    return_value=[
        {
            "file": "readme.md",
            "line": 10,
            "reference": "STALE_API",
            "type": "Stale Code Reference",
            "reason": "API symbol STALE_API not found",
        }
    ],
)
def test_main_with_drift(mock_check, mock_gather):
    with patch("sys.stdout") as mock_stdout:
        docs_drift.main()
    # Verified stdout write occurred
    assert mock_stdout.write.called

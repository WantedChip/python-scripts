"""Unit tests for the fixture-shrinker script."""

import gettext
import json
import sys
from typing import Any, List
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/fixture-shrinker")

# pylint: disable=wrong-import-position
from fixture_shrinker import (  # noqa: E402
    main,
    process_csv,
    process_json,
    process_text,
    run_validation,
    setup_logging,
    shrink_csv,
    shrink_json,
    shrink_text,
)


@pytest.fixture(autouse=True)
def _stub_gettext_catalog():
    """Stub gettext catalog loading so argparse never opens files via mocked open()."""
    with patch(
        "gettext.translation", lambda *args, **kwargs: gettext.NullTranslations()
    ):
        yield


def test_setup_logging() -> None:
    """Test setup_logging with verbose True and False."""
    setup_logging(verbose=True)
    setup_logging(verbose=False)


def test_run_validation_reproduced() -> None:
    """Test run_validation when the bug is reproduced (non-zero status)."""
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_run.return_value = mock_res

        assert run_validation("cmd {}", "temp.json") is True
        mock_run.assert_called_once_with(
            ["cmd", "temp.json"],
            stdout=-1,
            stderr=-1,
            text=True,
            check=False,
        )


def test_run_validation_passed() -> None:
    """Test run_validation when the bug is not reproduced (zero status)."""
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        assert run_validation("cmd {}", "temp.json") is False


def test_run_validation_error() -> None:
    """Test run_validation when subprocess raises an error."""
    with patch(
        "subprocess.run", side_effect=FileNotFoundError("not found")
    ) as mock_run:
        assert run_validation("cmd {}", "temp.json") is False
        mock_run.assert_called_once()


def test_shrink_json() -> None:
    """Test JSON shrinking behaves correctly by pruning keys/items."""
    data = {
        "keep": "buggy_value",
        "remove_me": "good_value",
        "nested": {"keep_nested": 42, "remove_nested": "unrelated"},
        "list": [1, 2, 3, 4],
    }

    def validate_fn(candidate: Any) -> bool:
        if not isinstance(candidate, dict) or "keep" not in candidate:
            return False
        if candidate["keep"] != "buggy_value":
            return False
        nested = candidate.get("nested")
        if not isinstance(nested, dict) or "keep_nested" not in nested:
            return False
        lst = candidate.get("list")
        if not isinstance(lst, list) or 3 not in lst:
            return False
        return True

    shrunk = shrink_json(data, validate_fn)
    assert shrunk == {
        "keep": "buggy_value",
        "nested": {"keep_nested": 0},
        "list": [3],
    }


def test_shrink_json_number_and_string() -> None:
    """Test shrinking numbers and strings in JSON structures."""
    assert shrink_json("test_string", lambda x: x == "") == ""
    assert shrink_json(100, lambda x: x == 0) == 0
    assert shrink_json(100, lambda x: isinstance(x, int) and x >= 10) == 10


def test_shrink_csv() -> None:
    """Test CSV row and column pruning."""
    header = ["id", "val", "extra"]
    rows = [
        ["1", "ok", "foo"],
        ["2", "fail", "bar"],
        ["3", "ok", "baz"],
    ]

    def validate_fn(candidate_rows: List[List[str]]) -> bool:
        for r in candidate_rows:
            if "fail" in r:
                return True
        return False

    shrunk = shrink_csv(rows, header, validate_fn)
    assert shrunk == [["fail"]]
    assert header == ["val"]


def test_shrink_text() -> None:
    """Test raw text pruning line by line."""
    lines = [
        "log line 1",
        "CRITICAL ERROR: db crashed",
        "log line 2",
    ]

    def validate_fn(candidate_lines: List[str]) -> bool:
        return any("CRITICAL ERROR" in line for line in candidate_lines)

    shrunk = shrink_text(lines, validate_fn)
    assert shrunk == ["CRITICAL ERROR: db crashed"]


def test_process_json(tmp_path: Any) -> None:
    """Test process_json parser, validation, and shrinking."""
    temp_file = str(tmp_path / "temp.json")
    # Invalid JSON
    with pytest.raises(SystemExit):
        process_json("invalid json", temp_file, "cmd {}")

    # Initial validation fails
    with patch("fixture_shrinker.run_validation", return_value=False):
        with pytest.raises(SystemExit):
            process_json('{"key": "value"}', temp_file, "cmd {}")

    # Success case
    with patch("fixture_shrinker.run_validation", return_value=True):
        m_open = mock_open()
        with patch("builtins.open", m_open):
            res = process_json('{"key": "value"}', temp_file, "cmd {}")
            assert json.loads(res) == {}


def test_process_csv(tmp_path: Any) -> None:
    """Test process_csv with header, without header, and empty inputs."""
    temp_file = str(tmp_path / "temp.csv")
    assert process_csv("", temp_file, "cmd {}", has_header=False) == ""

    # Initial validation fails
    with patch("fixture_shrinker.run_validation", return_value=False):
        with pytest.raises(SystemExit):
            process_csv("a,b\n1,2", temp_file, "cmd {}", has_header=True)

    # Success case with header
    with patch("fixture_shrinker.run_validation", return_value=True):
        m_open = mock_open()
        with patch("builtins.open", m_open):
            res = process_csv("a,b\n1,2", temp_file, "cmd {}", has_header=True)
            assert "b" in res or "2" in res


def test_process_text(tmp_path: Any) -> None:
    """Test process_text validation and output."""
    temp_file = str(tmp_path / "temp.txt")
    # Initial validation fails
    with patch("fixture_shrinker.run_validation", return_value=False):
        with pytest.raises(SystemExit):
            process_text("line1\nline2", temp_file, "cmd {}")

    # Success case
    with patch("fixture_shrinker.run_validation", return_value=True):
        m_open = mock_open()
        with patch("builtins.open", m_open):
            res = process_text("line1\nline2", temp_file, "cmd {}")
            assert isinstance(res, str)


@patch("os.path.exists", return_value=True)
def test_main_json_format(mock_exists: MagicMock) -> None:
    """Test main script logic for JSON format."""
    input_json = {"bug": True, "extra": "garbage"}
    m_open = mock_open(read_data=json.dumps(input_json))

    with patch("builtins.open", m_open), patch("subprocess.run") as mock_run:

        def side_effect(cmd_parts: List[str], **kwargs: Any) -> MagicMock:
            _ = cmd_parts[-1]
            mock_res = MagicMock()
            mock_res.returncode = 1
            return mock_res

        mock_run.side_effect = side_effect

        with patch(
            "sys.argv",
            [
                "fixture-shrinker",
                "--input",
                "f.json",
                "--output",
                "out.json",
                "--command",
                "validate {}",
                "-v",
            ],
        ):
            try:
                main()
            except SystemExit as exc:
                assert exc.code is None or exc.code == 0
            mock_exists.assert_any_call("f.json")


@patch("os.path.exists", return_value=True)
def test_main_csv_and_text_formats(mock_exists: MagicMock) -> None:
    """Test main CLI entrypoint for CSV and text format auto-detection."""
    m_open = mock_open(read_data="col1,col2\nval1,val2")
    with patch("builtins.open", m_open), patch(
        "fixture_shrinker.run_validation", return_value=True
    ):
        with patch(
            "sys.argv",
            [
                "fixture-shrinker",
                "--input",
                "data.csv",
                "--output",
                "out.csv",
                "--command",
                "validate {}",
                "--has-header",
            ],
        ):
            main()

    m_open_txt = mock_open(read_data="some text line")
    with patch("builtins.open", m_open_txt), patch(
        "fixture_shrinker.run_validation", return_value=True
    ):
        with patch(
            "sys.argv",
            [
                "fixture-shrinker",
                "--input",
                "data.txt",
                "--output",
                "out.txt",
                "--command",
                "validate {}",
            ],
        ):
            main()


@patch("os.path.exists", return_value=False)
def test_main_file_not_found(mock_exists: MagicMock) -> None:
    """Test main command fails when input file does not exist."""
    with patch(
        "sys.argv",
        [
            "fixture-shrinker",
            "--input",
            "missing.json",
            "--output",
            "out.json",
            "--command",
            "val {}",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

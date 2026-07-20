"""Unit tests for json_shape.py."""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Add import injection to resolve checkers package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import json_shape  # noqa: E402


def test_get_nested_paths_basic() -> None:
    """Test get_nested_paths with basic and nested structures."""
    data = {
        "a": 1,
        "b": "string",
        "c": True,
        "d": 1.5,
        "e": None,
        "f": {},
        "g": [],
        "h": {"nested_key": "val"},
        "i": [10, "mixed_list_element"],
    }

    paths = json_shape.get_nested_paths(data)

    expected = [
        ("a", "int"),
        ("b", "str"),
        ("c", "bool"),
        ("d", "float"),
        ("e", "null"),
        ("f", "empty_dict"),
        ("g", "empty_list"),
        ("h.nested_key", "str"),
        ("i[]", "int"),
        ("i[]", "str"),
    ]

    assert sorted(paths) == sorted(expected)


def test_get_nested_paths_unknown_type() -> None:
    """Test get_nested_paths with a custom class to trigger type fallback."""

    class CustomObject:
        pass

    obj = CustomObject()
    paths = json_shape.get_nested_paths(obj)
    assert paths == [("", "CustomObject")]


def test_analyze_records_empty() -> None:
    """Test analyze_records with empty list."""
    res = json_shape.analyze_records([])
    assert res == {
        "total_records": 0,
        "paths": {},
        "anomalies": [],
        "schema_drift": [],
    }


def test_analyze_records_anomalies_and_drift() -> None:
    """Test analyze_records to detect mixed types and rare fields."""
    # 25 records to allow for <5% frequency (1/25 = 4%)
    records = []

    # Standard records
    for i in range(24):
        records.append(
            {
                "id": i,
                "name": f"user_{i}",
                "age": (
                    float(i) if i % 2 == 0 else int(i)
                ),  # age has mixed type (float and int)
            }
        )

    # 25th record has a rare key "rare_key"
    records.append(
        {"id": 24, "name": "user_24", "age": 24, "rare_key": "special_value"}
    )

    analysis = json_shape.analyze_records(records)

    assert analysis["total_records"] == 25

    # Check mixed types anomaly on "age"
    anomalies = analysis["anomalies"]
    assert any(
        a["path"] == "age" and a["issue"] == "Mixed types found" for a in anomalies
    )

    # Check schema drift on "rare_key" (1/25 = 4% < 5%)
    drifts = analysis["schema_drift"]
    assert any(d["path"] == "rare_key" and d["frequency"] == 0.04 for d in drifts)


def test_print_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test print_report prints tables for required, common, optional, and drift."""
    analysis = {
        "total_records": 100,
        "paths": {
            "id": {"frequency": 1.0, "types": {"int": 100}, "is_mixed": False},
            "name": {"frequency": 0.95, "types": {"str": 95}, "is_mixed": False},
            "age": {
                "frequency": 0.50,
                "types": {"int": 40, "str": 10},
                "is_mixed": True,
            },
            "rare_field": {"frequency": 0.01, "types": {"bool": 1}, "is_mixed": False},
            "super_long_path_exceeding_table_header_width_limit": {
                "frequency": 1.0,
                "types": {"str": 100},
                "is_mixed": False,
            },
        },
        "anomalies": [
            {"path": "age", "issue": "Mixed types found", "details": "Types: int, str"}
        ],
        "schema_drift": [
            {"path": "rare_field", "frequency": 0.01, "count": 1, "types": ["bool"]}
        ],
    }

    json_shape.print_report(analysis, show_all=True)
    captured = capsys.readouterr().out

    assert "Required Fields (>=99% presence)" in captured
    assert "Common Fields (90% - 99% presence)" in captured
    assert "Optional Fields (5% - 90% presence)" in captured
    assert "Rare Fields / Schema Drift (<5% presence)" in captured
    assert "super_long_path_exceeding_table_hea" in captured
    assert "ANOMALIES DETECTED" in captured
    assert "SCHEMA DRIFT DETECTED" in captured


def test_print_report_no_anomalies_no_all(capsys: pytest.CaptureFixture[str]) -> None:
    """Test print_report output without anomalies and show_all=False."""
    analysis = {
        "total_records": 10,
        "paths": {
            "id": {"frequency": 1.0, "types": {"int": 10}, "is_mixed": False},
        },
        "anomalies": [],
        "schema_drift": [],
    }

    json_shape.print_report(analysis, show_all=False)
    captured = capsys.readouterr().out

    assert "No type structural anomalies detected" in captured
    assert "Optional Fields" not in captured
    assert "Rare Fields" not in captured


def test_main_file_input(tmp_path: Path) -> None:
    """Test main function reading from a JSON array file."""
    data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    file_path = tmp_path / "test.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    args = ["json_shape.py", str(file_path)]
    with patch("sys.argv", args):
        json_shape.main()


def test_main_file_json_lines(tmp_path: Path) -> None:
    """Test main function reading from a JSON lines file and saving output json."""
    lines = '{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}\n'
    file_path = tmp_path / "test.jsonl"
    file_path.write_text(lines, encoding="utf-8")

    output_json = tmp_path / "out.json"

    args = ["json_shape.py", str(file_path), "-j", str(output_json)]
    with patch("sys.argv", args):
        json_shape.main()

    assert output_json.exists()
    saved_data = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved_data["total_records"] == 2


def test_main_stdin() -> None:
    """Test main function reading from stdin."""
    data = '[{"id": 1}]'
    args = ["json_shape.py"]

    with patch("sys.argv", args):
        with patch("sys.stdin", StringIO(data)):
            with patch("sys.stdin.isatty", return_value=False):
                json_shape.main()


def test_main_empty_input(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main function handling empty input."""
    args = ["json_shape.py"]

    with patch("sys.argv", args):
        with patch("sys.stdin", StringIO("")):
            with patch("sys.stdin.isatty", return_value=False):
                with pytest.raises(SystemExit) as exc:
                    json_shape.main()
                assert exc.value.code == 1


def test_main_invalid_json_array(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main function handling invalid JSON array format."""
    file_path = tmp_path / "invalid.json"
    file_path.write_text("[{'id': 1}", encoding="utf-8")  # single quotes, invalid json

    args = ["json_shape.py", str(file_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            json_shape.main()
        assert exc.value.code == 1

    err = capsys.readouterr().err
    assert "Invalid JSON Array format" in err


def test_main_invalid_json_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main function handling invalid JSON Lines format."""
    file_path = tmp_path / "invalid.jsonl"
    file_path.write_text('{"id": 1}\n{"id": 2, invalid}\n', encoding="utf-8")

    args = ["json_shape.py", str(file_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            json_shape.main()
        assert exc.value.code == 1

    err = capsys.readouterr().err
    assert "Invalid JSON Line 2" in err


def test_main_file_read_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main function handling file reading (OSError) error."""
    args = ["json_shape.py", str(tmp_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            json_shape.main()
        assert exc.value.code == 1

    err = capsys.readouterr().err
    assert "Error reading file" in err


def test_main_json_save_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main function handling error when writing JSON output."""
    file_path = tmp_path / "test.json"
    file_path.write_text('[{"id": 1}]', encoding="utf-8")

    args = ["json_shape.py", str(file_path), "-j", str(tmp_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            json_shape.main()
        assert exc.value.code == 1

    err = capsys.readouterr().err
    assert "Error saving JSON analysis output" in err

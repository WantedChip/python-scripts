import io
import os
import sys
from unittest.mock import mock_open, patch

# Add the path to tools/data-diff-human to sys.path so we can import from it
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_diff_human import (  # noqa: E402
    compare_records,
    generate_human_summary,
    load_data,
    main,
)


def test_load_data_json_array():
    content = '[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]'
    with patch("builtins.open", mock_open(read_data=content)):
        records = load_data("fake_path.json")
    assert records == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


def test_load_data_json_lines():
    content = '{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}'
    with patch("builtins.open", mock_open(read_data=content)):
        records = load_data("fake_path.jsonl")
    assert records == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


def test_load_data_csv_comma():
    content = "id,name\n1,Alice\n2,Bob"
    file_mock1 = io.StringIO(content)
    file_mock2 = io.StringIO(content)

    with patch("builtins.open", side_effect=[file_mock1, file_mock2]):
        records = load_data("fake_path.csv")
    assert records == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]


def test_load_data_csv_semicolon():
    content = "id;name\n1;Alice\n2;Bob"
    file_mock1 = io.StringIO(content)
    file_mock2 = io.StringIO(content)

    with patch("builtins.open", side_effect=[file_mock1, file_mock2]):
        records = load_data("fake_path.csv")
    assert records == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]


def test_load_data_failure():
    file_mock1 = io.StringIO("not json")

    def side_effect(path, *args, **kwargs):
        if side_effect.called == 0:
            side_effect.called += 1
            return file_mock1
        raise OSError("CSV open failed")

    side_effect.called = 0

    with patch("builtins.open", side_effect=side_effect):
        with patch("sys.stderr"):
            try:
                load_data("fake_path.csv")
            except SystemExit as exc_info:
                assert exc_info.code == 1


def test_compare_records_basic():
    records1 = [
        {"id": "1", "name": "Alice", "age": "30", "score": "95.5", "secret": "foo"},
        {"id": "2", "name": "Bob", "age": "25", "score": "80.0", "secret": "bar"},
    ]
    records2 = [
        {"id": "2", "name": "Bobby", "age": "25", "score": "82.0", "secret": "baz"},
        {"id": "3", "name": "Charlie", "age": "40", "score": "90.0", "secret": "qux"},
    ]

    res = compare_records(
        records1,
        records2,
        key_field="id",
        numeric_cols={"age", "score"},
        exclude_cols={"secret"},
        tolerance=1.0,
    )

    assert res["added"] == 1
    assert res["removed"] == 1
    assert res["modified"] == 1
    assert "score" in res["numeric_changes"]
    assert res["numeric_changes"]["score"] == [(80.0, 82.0, 2.0, 2.5)]
    assert "age" not in res["numeric_changes"]
    assert "name" in res["text_changes"]
    assert res["text_changes"]["name"] == [("Bob", "Bobby")]


def test_compare_records_tolerance():
    records1 = [{"id": "1", "val": "100"}]
    records2 = [{"id": "1", "val": "100.5"}]

    res_no_tol = compare_records(records1, records2, "id", set(), set(), 0.0)
    assert res_no_tol["modified"] == 1
    assert "val" in res_no_tol["numeric_changes"]

    res_with_tol = compare_records(records1, records2, "id", set(), set(), 1.0)
    assert res_with_tol["modified"] == 0
    assert "val" not in res_with_tol["numeric_changes"]


def test_compare_records_comma_numbers():
    records1 = [{"id": "1", "val": "1,000"}]
    records2 = [{"id": "1", "val": "2,000"}]
    res = compare_records(records1, records2, "id", set(), set(), 0.0)
    assert res["modified"] == 1
    assert res["numeric_changes"]["val"] == [(1000.0, 2000.0, 1000.0, 100.0)]


def test_compare_records_missing_key():
    records1 = [{"name": "Alice"}]
    records2 = [{"id": "1", "name": "Alice"}]
    res = compare_records(records1, records2, "id", set(), set(), 0.0)
    assert res["added"] == 1
    assert res["removed"] == 0
    assert res["modified"] == 0


def test_compare_records_dynamic_nan_and_nones():
    records1 = [{"id": "1", "val": "not-a-number", "val2": None, "val3": "50"}]
    records2 = [{"id": "1", "val": "100", "val2": "200", "val3": None}]
    res = compare_records(records1, records2, "id", set(), set(), 0.0)

    assert "val" in res["text_changes"]
    assert res["text_changes"]["val"] == [("not-a-number", "100")]

    assert "val2" in res["numeric_changes"]
    assert res["numeric_changes"]["val2"] == [(0.0, 200.0, 200.0, 100.0)]

    assert "val3" in res["numeric_changes"]
    assert res["numeric_changes"]["val3"] == [(50.0, 0.0, -50.0, -100.0)]


def test_generate_human_summary_no_changes():
    report = {
        "added": 0,
        "removed": 0,
        "modified": 0,
        "numeric_changes": {},
        "text_changes": {},
    }
    summary = generate_human_summary(report)
    assert summary == "No changes detected. The datasets are identical."


def test_generate_human_summary_with_changes():
    report = {
        "added": 5,
        "removed": 2,
        "modified": 3,
        "numeric_changes": {
            "val": [(10.0, 20.0, 10.0, 100.0), (30.0, 15.0, -15.0, -50.0)]
        },
        "text_changes": {
            "status": [
                ("active", "inactive"),
                ("active", "pending"),
                ("active", "inactive"),
            ]
        },
    }
    summary = generate_human_summary(report)
    assert (
        "Executive Summary: 5 rows added, 2 records disappeared, 3 records modified."
        in summary
    )
    assert "Column 'val': 2 values modified (1 increased, 1 decreased)." in summary
    assert "Average change: -2.50 (+25.0%)." in summary
    assert "Column 'status': 3 text values changed." in summary
    expected_transitions = (
        "Top transitions: 'active' -> 'inactive' (2 times), "
        "'active' -> 'pending' (1 times)"
    )
    assert expected_transitions in summary


def test_main():
    with patch("data_diff_human.load_data") as mock_load, patch(
        "data_diff_human.compare_records"
    ) as mock_compare, patch(
        "data_diff_human.generate_human_summary"
    ) as mock_summary, patch(
        "builtins.print"
    ) as mock_print, patch(
        "sys.argv",
        [
            "data_diff_human.py",
            "f1.csv",
            "f2.csv",
            "-k",
            "id",
            "-n",
            "val",
            "-t",
            "1.5",
            "-e",
            "secret",
        ],
    ):

        mock_load.side_effect = [
            [{"id": "1", "val": "10", "secret": "a"}],
            [{"id": "1", "val": "12", "secret": "b"}],
        ]
        mock_compare.return_value = {
            "added": 0,
            "removed": 0,
            "modified": 1,
            "numeric_changes": {},
            "text_changes": {},
        }
        mock_summary.return_value = "Mocked Summary Output"

        main()

        mock_load.assert_any_call("f1.csv")
        mock_load.assert_any_call("f2.csv")
        mock_compare.assert_called_once_with(
            [{"id": "1", "val": "10", "secret": "a"}],
            [{"id": "1", "val": "12", "secret": "b"}],
            "id",
            {"val"},
            {"secret"},
            1.5,
        )
        mock_summary.assert_called_once_with(mock_compare.return_value)
        mock_print.assert_called_once_with("Mocked Summary Output")

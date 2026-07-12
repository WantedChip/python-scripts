"""Tests for data_pipeline_diff.py."""

# pylint: disable=wrong-import-position,import-error,missing-class-docstring
# pylint: disable=missing-function-docstring,unused-import,unused-variable
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_pipeline_diff import (  # noqa: E402
    DiffResult,
    auto_discover_keys,
    color_text,
    compare_datasets,
    flatten_data,
    format_text_table,
    generate_html_report,
    generate_json_report,
    generate_text_report,
    is_numeric_match,
    load_csv_source,
    load_json_source,
    load_source,
    load_sqlite_source,
    setup_logging,
)


# ---------------------------------------------------------------------------
# flatten_data
# ---------------------------------------------------------------------------
class TestFlattenData:
    def test_simple_dict(self) -> None:
        data = {"a": 1, "b": 2}
        assert flatten_data(data) == {"a": 1, "b": 2}

    def test_nested_dict(self) -> None:
        data = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
        expected = {"a": 1, "b.c": 2, "b.d.e": 3}
        assert flatten_data(data) == expected

    def test_list_in_dict(self) -> None:
        data = {"a": [10, 20], "b": {"c": [30, 40]}}
        expected = {"a.0": 10, "a.1": 20, "b.c.0": 30, "b.c.1": 40}
        assert flatten_data(data) == expected

    def test_nested_list(self) -> None:
        data = [[1, 2], [3, 4]]
        expected = {"0.0": 1, "0.1": 2, "1.0": 3, "1.1": 4}
        assert flatten_data(data) == expected


# ---------------------------------------------------------------------------
# is_numeric_match
# ---------------------------------------------------------------------------
class TestNumericMatch:
    def test_exact_match(self) -> None:
        assert is_numeric_match(10, 10, 0.0) is True
        assert is_numeric_match("10", "10", 0.0) is True

    def test_within_tolerance(self) -> None:
        assert is_numeric_match(10.0001, 10.0002, 0.001) is True
        assert is_numeric_match("10.0001", "10.0002", 0.001) is True

    def test_outside_tolerance(self) -> None:
        assert is_numeric_match(10.0, 11.0, 0.1) is False

    def test_non_numeric(self) -> None:
        assert is_numeric_match("apple", "orange", 0.1) is False
        assert is_numeric_match("apple", "apple", 0.1) is True


# ---------------------------------------------------------------------------
# Loaders (CSV, JSON, SQLite)
# ---------------------------------------------------------------------------
class TestLoaders:
    def test_load_csv(self, tmp_path) -> None:
        f = tmp_path / "test.csv"
        f.write_text("id,name\n1,Alice\n2,Bob", encoding="utf-8")
        data = load_csv_source(f)
        assert data == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]

    def test_load_json_list(self, tmp_path) -> None:
        f = tmp_path / "test.json"
        data_in = [{"id": 1, "meta": {"val": "x"}}, {"id": 2, "meta": {"val": "y"}}]
        f.write_text(json.dumps(data_in), encoding="utf-8")
        data = load_json_source(f)
        assert data == [{"id": 1, "meta.val": "x"}, {"id": 2, "meta.val": "y"}]

    def test_load_json_single(self, tmp_path) -> None:
        f = tmp_path / "test.json"
        data_in = {"id": 1, "meta": {"val": "x"}}
        f.write_text(json.dumps(data_in), encoding="utf-8")
        data = load_json_source(f)
        assert data == [{"id": 1, "meta.val": "x"}]

    def test_load_sqlite(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob')")
        conn.commit()
        conn.close()

        data = load_sqlite_source(db_path, table="users")
        assert len(data) == 2
        assert data[0]["name"] == "Alice"


# ---------------------------------------------------------------------------
# compare_datasets
# ---------------------------------------------------------------------------
class TestCompareDatasets:
    def test_identical_datasets(self) -> None:
        data1 = [{"id": "1", "val": "A"}, {"id": "2", "val": "B"}]
        data2 = [{"id": "1", "val": "A"}, {"id": "2", "val": "B"}]
        res = compare_datasets(data1, data2, keys=["id"])
        assert res.identical_count == 2
        assert len(res.added_records) == 0
        assert len(res.removed_records) == 0
        assert len(res.modifications) == 0

    def test_added_and_removed(self) -> None:
        data1 = [{"id": "1", "val": "A"}, {"id": "2", "val": "B"}]
        data2 = [{"id": "1", "val": "A"}, {"id": "3", "val": "C"}]
        res = compare_datasets(data1, data2, keys=["id"])
        assert len(res.added_records) == 1
        assert res.added_records[0]["id"] == "3"
        assert len(res.removed_records) == 1
        assert res.removed_records[0]["id"] == "2"

    def test_modifications(self) -> None:
        data1 = [{"id": "1", "val": "A", "score": 10}]
        data2 = [{"id": "1", "val": "B", "score": 11}]
        res = compare_datasets(data1, data2, keys=["id"])
        assert len(res.modifications) == 1
        mods = res.modifications[("1",)]
        assert any(
            m["field"] == "val" and m["old"] == "A" and m["new"] == "B" for m in mods
        )
        assert any(
            m["field"] == "score" and m["old"] == 10 and m["new"] == 11 for m in mods
        )

    def test_numeric_tolerance(self) -> None:
        data1 = [{"id": "1", "val": 10.0001}]
        data2 = [{"id": "1", "val": 10.0002}]
        # No tolerance -> should be modified
        res_no_tol = compare_datasets(data1, data2, keys=["id"], tolerance=0.0)
        assert len(res_no_tol.modifications) == 1
        # With tolerance -> should be identical
        res_tol = compare_datasets(data1, data2, keys=["id"], tolerance=0.001)
        assert res_tol.identical_count == 1

    def test_exclude_columns(self) -> None:
        data1 = [{"id": "1", "val": "A", "ts": "2023-01-01"}]
        data2 = [{"id": "1", "val": "A", "ts": "2023-01-02"}]
        # Exclude 'ts' -> identical
        res = compare_datasets(data1, data2, keys=["id"], exclude=["ts"])
        assert res.identical_count == 1

    def test_composite_keys(self) -> None:
        data1 = [
            {"id": "1", "cat": "X", "val": "A"},
            {"id": "2", "cat": "Y", "val": "B"},
        ]
        data2 = [
            {"id": "1", "cat": "X", "val": "A"},
            {"id": "2", "cat": "Y", "val": "C"},
        ]
        res = compare_datasets(data1, data2, keys=["id", "cat"])
        assert len(res.modifications) == 1
        assert ("2", "Y") in res.modifications

    def test_no_keys_fallback_to_index(self) -> None:
        data1 = [{"val": "A"}, {"val": "B"}]
        data2 = [{"val": "A"}, {"val": "C"}]
        res = compare_datasets(data1, data2)
        assert res.keys == ["__row_index__"]
        assert len(res.modifications) == 1
        assert ("1",) in res.modifications

    def test_schema_drift(self) -> None:
        data1 = [{"id": "1", "val": "A"}]
        data2 = [{"id": "1", "val": "A", "new_col": "X"}]
        res = compare_datasets(data1, data2, keys=["id"])
        assert "new_col" in res.added_columns
        assert len(res.removed_columns) == 0

    def test_auto_discover_keys(self) -> None:
        h1 = ["id", "name", "email"]
        h2 = ["id", "name", "email"]
        from data_pipeline_diff import auto_discover_keys

        assert auto_discover_keys(h1, h2) == ["id"]

        h3 = ["uuid", "name"]
        h4 = ["uuid", "name"]
        assert auto_discover_keys(h3, h4) == ["uuid"]

        h5 = ["name"]
        h6 = ["name"]
        assert auto_discover_keys(h5, h6) is None


# ---------------------------------------------------------------------------
# format_text_table
# ---------------------------------------------------------------------------
class TestFormatTextTable:
    def test_empty_headers(self) -> None:
        assert format_text_table([], []) == ""

    def test_basic_table(self) -> None:
        headers = ["Name", "Age"]
        rows = [["Alice", "30"], ["Bob", "25"]]
        result = format_text_table(headers, rows)
        assert "Name" in result
        assert "Alice" in result
        assert "Bob" in result
        assert "+" in result  # border chars
        assert "|" in result

    def test_row_shorter_than_headers(self) -> None:
        headers = ["A", "B", "C"]
        rows = [["1", "2"]]
        result = format_text_table(headers, rows)
        assert "A" in result
        assert "C" in result


# ---------------------------------------------------------------------------
# color_text
# ---------------------------------------------------------------------------
class TestColorText:
    def test_no_color_flag(self) -> None:
        assert color_text("hello", "31", no_color=True) == "hello"

    def test_with_color(self, monkeypatch) -> None:
        # Mock isatty to return True for color output
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        result = color_text("hello", "31", no_color=False)
        # ANSI escape codes
        assert "\033[31m" in result
        assert "\033[0m" in result
        assert "hello" in result


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------
class TestSetupLogging:
    def test_verbose_true(self) -> None:
        import logging

        import data_pipeline_diff as dpd

        # Reset the module logger
        dpd.logger.handlers.clear()
        setup_logging(True)
        assert dpd.logger.level == logging.DEBUG

    def test_verbose_false(self) -> None:
        import logging

        import data_pipeline_diff as dpd

        dpd.logger.handlers.clear()
        setup_logging(False)
        assert dpd.logger.level == logging.INFO


# ---------------------------------------------------------------------------
# generate_text_report
# ---------------------------------------------------------------------------
class TestGenerateTextReport:
    def _make_result(self) -> DiffResult:
        return DiffResult(
            headers_a=["id", "val"],
            headers_b=["id", "val"],
            added_columns=[],
            removed_columns=[],
            common_columns=["id", "val"],
            total_rows_a=2,
            total_rows_b=2,
            keys=["id"],
            added_records=[{"id": "3", "val": "C"}],
            removed_records=[{"id": "1", "val": "A"}],
            modifications={("2",): [{"field": "val", "old": "B", "new": "X"}]},
            identical_count=0,
        )

    def test_basic_report(self) -> None:
        res = self._make_result()
        report = generate_text_report(res, no_color=True)
        assert "DATA PIPELINE DIFF REPORT" in report
        assert "Primary Keys Used: id" in report
        assert "Source A Rows: 2" in report
        assert "Added Rows:" in report
        assert "Removed Rows:" in report
        assert "MODIFIED CELL DETAILS" in report
        assert "val" in report
        assert "B" in report
        assert "X" in report

    def test_summary_only(self) -> None:
        res = self._make_result()
        report = generate_text_report(res, no_color=True, summary_only=True)
        assert "CHANGE SUMMARY:" in report
        assert "ADDED RECORDS:" not in report
        assert "REMOVED RECORDS:" not in report
        assert "MODIFIED CELL DETAILS" not in report

    def test_schema_drift(self) -> None:
        res = self._make_result()
        res.added_columns = ["new_col"]
        res.removed_columns = ["old_col"]
        report = generate_text_report(res, no_color=True)
        assert "SCHEMA DRIFT DETECTED" in report
        assert "new_col" in report
        assert "old_col" in report


# ---------------------------------------------------------------------------
# generate_json_report
# ---------------------------------------------------------------------------
class TestGenerateJsonReport:
    def _make_result(self) -> DiffResult:
        return DiffResult(
            headers_a=["id", "val"],
            headers_b=["id", "val", "extra"],
            added_columns=["extra"],
            removed_columns=[],
            common_columns=["id", "val"],
            total_rows_a=1,
            total_rows_b=2,
            keys=["id"],
            added_records=[{"id": "2", "val": "B", "extra": "E"}],
            removed_records=[],
            modifications={("1",): [{"field": "val", "old": "A", "new": "X"}]},
            identical_count=0,
        )

    def test_json_output(self) -> None:
        res = self._make_result()
        json_str = generate_json_report(res)
        data = json.loads(json_str)
        assert data["summary"]["total_rows_source_a"] == 1
        assert data["summary"]["total_rows_source_b"] == 2
        assert data["summary"]["added_rows"] == 1
        assert data["summary"]["removed_rows"] == 0
        assert data["summary"]["modified_rows"] == 1
        assert data["schema_drift"]["added_columns"] == ["extra"]
        assert "1" in data["modified_details"]
        assert data["added_records"][0]["id"] == "2"


# ---------------------------------------------------------------------------
# generate_html_report
# ---------------------------------------------------------------------------
class TestGenerateHtmlReport:
    def _make_result(self) -> DiffResult:
        return DiffResult(
            headers_a=["id", "val"],
            headers_b=["id", "val"],
            added_columns=[],
            removed_columns=[],
            common_columns=["id", "val"],
            total_rows_a=1,
            total_rows_b=1,
            keys=["id"],
            added_records=[],
            removed_records=[],
            modifications={("1",): [{"field": "val", "old": "A", "new": "B"}]},
            identical_count=0,
        )

    def test_html_structure(self) -> None:
        res = self._make_result()
        html = generate_html_report(res, "source_a.csv", "source_b.csv")
        assert "<!DOCTYPE html>" in html
        assert "Data Pipeline Diff Report" in html
        assert "source_a.csv" in html
        assert "source_b.csv" in html
        assert "Modified Cells" in html
        assert "Added Rows" in html
        assert "Removed Rows" in html
        assert "Schema Drift" in html
        assert "filterTable" in html
        assert "switchTab" in html
        assert "A" in html
        assert "B" in html

    def test_html_no_modifications(self) -> None:
        res = DiffResult(
            headers_a=["id", "val"],
            headers_b=["id", "val"],
            added_columns=[],
            removed_columns=[],
            common_columns=["id", "val"],
            total_rows_a=1,
            total_rows_b=1,
            keys=["id"],
            added_records=[],
            removed_records=[],
            modifications={},
            identical_count=1,
        )
        html = generate_html_report(res, "a.csv", "b.csv")
        assert "No rows modified" in html


# ---------------------------------------------------------------------------
# load_source
# ---------------------------------------------------------------------------
class TestLoadSource:
    def test_auto_detect_csv(self, tmp_path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("id,val\n1,A", encoding="utf-8")
        data = load_source(f)
        assert data == [{"id": "1", "val": "A"}]

    def test_auto_detect_json(self, tmp_path) -> None:
        f = tmp_path / "data.json"
        f.write_text('[{"id": 1}]', encoding="utf-8")
        data = load_source(f)
        assert data == [{"id": 1}]

    def test_auto_detect_sqlite(self, tmp_path) -> None:
        f = tmp_path / "data.db"
        conn = sqlite3.connect(str(f))
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
        data = load_source(f, table="t")
        assert data == [{"id": 1}]

    def test_explicit_format(self, tmp_path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("id,val\n1,A", encoding="utf-8")
        data = load_source(f, fmt="csv")
        assert data == [{"id": "1", "val": "A"}]

    def test_unknown_extension_raises(self, tmp_path) -> None:
        f = tmp_path / "data.xyz"
        f.write_text("foo", encoding="utf-8")
        try:
            load_source(f)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Could not automatically detect format" in str(e)


# ---------------------------------------------------------------------------
# Error paths and edge cases in loaders
# ---------------------------------------------------------------------------
class TestLoaderErrors:
    def test_load_csv_utf8_fallback(self, tmp_path) -> None:
        """Test latin-1 fallback when UTF-8 fails."""
        f = tmp_path / "bad.csv"
        # Write bytes that are valid latin-1 but not UTF-8
        f.write_bytes(b"id,val\n1,\xe9\n")  # \xe9 is 'é' in latin-1
        data = load_csv_source(f)
        assert data == [{"id": "1", "val": "\xe9"}]

    def test_load_csv_empty_file(self, tmp_path) -> None:
        f = tmp_path / "empty.csv"
        f.write_text("", encoding="utf-8")
        try:
            load_csv_source(f)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "no headers or is empty" in str(e)

    def test_load_json_invalid(self, tmp_path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("not valid json", encoding="utf-8")
        try:
            load_json_source(f)
            assert False, "Should have raised ValueError"
        except (ValueError, json.JSONDecodeError) as e:
            # json.JSONDecodeError is a subclass of ValueError
            assert "JSON must be a list of records or a dictionary object" in str(
                e
            ) or "Expecting value" in str(e)

    def test_load_json_non_list_non_dict(self, tmp_path) -> None:
        f = tmp_path / "bad.json"
        f.write_text('"just a string"', encoding="utf-8")
        try:
            load_json_source(f)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "JSON must be a list of records or a dictionary object" in str(e)


# ---------------------------------------------------------------------------
# compare_datasets edge cases
# ---------------------------------------------------------------------------
class TestCompareDatasetsEdgeCases:
    def test_auto_discover_keys_none(self) -> None:
        """Test auto_discover_keys returns None when no common key found."""
        h1 = ["name", "email"]
        h2 = ["name", "email"]
        assert auto_discover_keys(h1, h2) is None

    def test_modification_with_missing_keys(self) -> None:
        """Test modification detection when columns differ per row."""
        data1 = [{"id": "1", "val": "A", "extra": "X"}]
        data2 = [{"id": "1", "val": "B"}]  # missing 'extra'
        res = compare_datasets(data1, data2, keys=["id"])
        assert len(res.modifications) == 1
        mods = res.modifications[("1",)]
        assert any(
            m["field"] == "extra" and m["old"] == "X" and m["new"] is None for m in mods
        )

    def test_modification_with_missing_keys_b(self) -> None:
        data1 = [{"id": "1", "val": "A"}]
        data2 = [{"id": "1", "val": "B", "extra": "Y"}]  # has extra
        res = compare_datasets(data1, data2, keys=["id"])
        assert len(res.modifications) == 1
        mods = res.modifications[("1",)]
        assert any(
            m["field"] == "extra" and m["old"] is None and m["new"] == "Y" for m in mods
        )


# ---------------------------------------------------------------------------
# generate_text_report edge cases
# ---------------------------------------------------------------------------
class TestGenerateTextReportEdgeCases:
    def _make_result(self) -> DiffResult:
        return DiffResult(
            headers_a=["id", "val"],
            headers_b=["id", "val"],
            added_columns=[],
            removed_columns=[],
            common_columns=["id", "val"],
            total_rows_a=2,
            total_rows_b=2,
            keys=["id"],
            added_records=[{"id": "3", "val": "C"}],
            removed_records=[{"id": "1", "val": "A"}],
            modifications={("2",): [{"field": "val", "old": "B", "new": "X"}]},
            identical_count=0,
        )

    def test_added_records_truncation(self) -> None:
        """Test that added records are truncated at 20."""
        res = self._make_result()
        res.added_records = [{"id": str(i), "val": f"V{i}"} for i in range(25)]
        report = generate_text_report(res, no_color=True)
        assert "... and 5 more added records" in report

    def test_removed_records_truncation(self) -> None:
        res = self._make_result()
        res.removed_records = [{"id": str(i), "val": f"V{i}"} for i in range(25)]
        report = generate_text_report(res, no_color=True)
        assert "... and 5 more removed records" in report

    def test_modified_cells_truncation(self) -> None:
        res = self._make_result()
        # Create 60 modifications (50 limit + 10 more)
        mods = {}
        for i in range(60):
            mods[(str(i),)] = [{"field": "val", "old": "A", "new": "B"}]
        res.modifications = mods
        report = generate_text_report(res, no_color=True)
        assert "... and 10 more modified cells" in report


# ---------------------------------------------------------------------------
# generate_html_report edge cases
# ---------------------------------------------------------------------------
class TestGenerateHtmlReportEdgeCases:
    def _make_result(self) -> DiffResult:
        return DiffResult(
            headers_a=["id", "val"],
            headers_b=["id", "val"],
            added_columns=[],
            removed_columns=[],
            common_columns=["id", "val"],
            total_rows_a=1,
            total_rows_b=1,
            keys=["id"],
            added_records=[{"id": "2", "val": "B"}],
            removed_records=[{"id": "1", "val": "A"}],
            modifications={("3",): [{"field": "val", "old": "C", "new": "D"}]},
            identical_count=0,
        )

    def test_html_with_added_removed(self) -> None:
        res = self._make_result()
        html = generate_html_report(res, "a.csv", "b.csv")
        assert "Added Rows" in html
        assert "Removed Rows" in html
        assert "B" in html
        assert "A" in html

    def test_html_with_schema_drift(self) -> None:
        res = DiffResult(
            headers_a=["id", "val"],
            headers_b=["id", "val", "new_col"],
            added_columns=["new_col"],
            removed_columns=["old_col"],
            common_columns=["id", "val"],
            total_rows_a=1,
            total_rows_b=1,
            keys=["id"],
            added_records=[],
            removed_records=[],
            modifications={},
            identical_count=1,
        )
        html = generate_html_report(res, "a.csv", "b.csv")
        assert "new_col" in html
        assert "old_col" in html
        assert "Added Columns" in html
        assert "Removed Columns" in html


# ---------------------------------------------------------------------------
# Main CLI tests
# ---------------------------------------------------------------------------
class TestMainCLI:
    def test_main_csv_comparison(self, tmp_path, monkeypatch) -> None:
        """Test main function with CSV files."""
        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        f1.write_text("id,val\n1,A\n2,B", encoding="utf-8")
        f2.write_text("id,val\n1,A\n2,C", encoding="utf-8")

        import sys
        from io import StringIO

        monkeypatch.setattr(sys, "argv", ["prog", str(f1), str(f2), "--key", "id"])
        monkeypatch.setattr(sys, "stdout", StringIO())
        from data_pipeline_diff import main

        try:
            main()
        except SystemExit:
            pass
        output = sys.stdout.getvalue()
        assert "Modified Cells" in output or "Modified Rows" in output

    def test_main_missing_file(self, tmp_path, monkeypatch) -> None:
        """Test main with missing source file."""
        import sys
        from io import StringIO

        monkeypatch.setattr(sys, "argv", ["prog", "nonexistent.csv", "other.csv"])
        monkeypatch.setattr(sys, "stdout", StringIO())
        monkeypatch.setattr(sys, "stderr", StringIO())
        from data_pipeline_diff import main

        try:
            main()
        except SystemExit as e:
            assert e.code == 1

    def test_main_missing_source2(self, tmp_path, monkeypatch) -> None:
        f1 = tmp_path / "a.csv"
        f1.write_text("id,val\n1,A", encoding="utf-8")
        import sys
        from io import StringIO

        monkeypatch.setattr(sys, "argv", ["prog", str(f1)])
        monkeypatch.setattr(sys, "stdout", StringIO())
        monkeypatch.setattr(sys, "stderr", StringIO())
        from data_pipeline_diff import main

        try:
            main()
        except SystemExit as e:
            assert e.code == 1

    def test_main_json_output(self, tmp_path, monkeypatch) -> None:
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text('[{"id": 1, "val": "A"}]', encoding="utf-8")
        f2.write_text('[{"id": 1, "val": "B"}]', encoding="utf-8")
        import sys
        from io import StringIO

        monkeypatch.setattr(
            sys,
            "argv",
            ["prog", str(f1), str(f2), "--key", "id", "--out-format", "json"],
        )
        monkeypatch.setattr(sys, "stdout", StringIO())
        from data_pipeline_diff import main

        try:
            main()
        except SystemExit:
            pass
        output = sys.stdout.getvalue()
        assert "modified_rows" in output

    def test_main_html_output(self, tmp_path, monkeypatch) -> None:
        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        f1.write_text("id,val\n1,A", encoding="utf-8")
        f2.write_text("id,val\n1,A", encoding="utf-8")
        out_file = tmp_path / "report.html"
        import sys
        from io import StringIO

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "prog",
                str(f1),
                str(f2),
                "--key",
                "id",
                "--out-format",
                "html",
                "--output",
                str(out_file),
            ],
        )
        monkeypatch.setattr(sys, "stdout", StringIO())
        from data_pipeline_diff import main

        try:
            main()
        except SystemExit:
            pass
        html_content = out_file.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html_content

    def test_main_sqlite_same_db(self, tmp_path, monkeypatch) -> None:
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE t1 (id INTEGER, val TEXT)")
        conn.execute("CREATE TABLE t2 (id INTEGER, val TEXT)")
        conn.execute("INSERT INTO t1 VALUES (1, 'A')")
        conn.execute("INSERT INTO t2 VALUES (1, 'B')")
        conn.commit()
        conn.close()
        import sys
        from io import StringIO

        monkeypatch.setattr(
            sys,
            "argv",
            ["prog", str(db), "--table1", "t1", "--table2", "t2", "--key", "id"],
        )
        monkeypatch.setattr(sys, "stdout", StringIO())
        from data_pipeline_diff import main

        try:
            main()
        except SystemExit:
            pass
        output = sys.stdout.getvalue()
        assert "Modified" in output or "Modified Rows" in output

    def test_main_sqlite_same_db_missing_tables(self, tmp_path, monkeypatch) -> None:
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()
        import sys
        from io import StringIO

        monkeypatch.setattr(sys, "argv", ["prog", str(db)])
        monkeypatch.setattr(sys, "stdout", StringIO())
        monkeypatch.setattr(sys, "stderr", StringIO())
        from data_pipeline_diff import main

        try:
            main()
        except SystemExit as e:
            assert e.code == 1

"""Tests for csv_cleaner.py."""

import csv
import io
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from csv_cleaner import (
    AnalysisReport,
    ColumnStats,
    detect_delimiter,
    is_null,
    infer_type,
    matches_type,
    analyze_csv,
    clean_csv,
)


# ---------------------------------------------------------------------------
# detect_delimiter
# ---------------------------------------------------------------------------
class TestDetectDelimiter:
    def test_comma(self) -> None:
        assert detect_delimiter("a,b,c\n1,2,3\n") == ","

    def test_tab(self) -> None:
        assert detect_delimiter("a\tb\tc\n1\t2\t3\n") == "\t"

    def test_semicolon(self) -> None:
        assert detect_delimiter("a;b;c\n1;2;3\n") == ";"

    def test_pipe(self) -> None:
        assert detect_delimiter("a|b|c\n1|2|3\n") == "|"

    def test_fallback_to_comma(self) -> None:
        # Ambiguous content should fall back to comma
        result = detect_delimiter("hello")
        assert result == ","


# ---------------------------------------------------------------------------
# is_null
# ---------------------------------------------------------------------------
class TestIsNull:
    def test_empty_string(self) -> None:
        assert is_null("") is True

    def test_null_literal(self) -> None:
        assert is_null("null") is True
        assert is_null("NULL") is True

    def test_na(self) -> None:
        assert is_null("N/A") is True
        assert is_null("na") is True

    def test_nan(self) -> None:
        assert is_null("NaN") is True

    def test_real_value(self) -> None:
        assert is_null("hello") is False
        assert is_null("0") is False
        assert is_null("123") is False


# ---------------------------------------------------------------------------
# infer_type
# ---------------------------------------------------------------------------
class TestInferType:
    def test_integers(self) -> None:
        assert infer_type(["1", "2", "3", "4", "5"]) == "int"

    def test_floats(self) -> None:
        assert infer_type(["1.1", "2.2", "3.3"]) == "float"

    def test_dates(self) -> None:
        assert infer_type(["2023-01-01", "2023-12-31", "2024-06-15"]) == "date"

    def test_booleans(self) -> None:
        assert infer_type(["true", "false", "true", "false"]) == "bool"

    def test_strings(self) -> None:
        assert infer_type(["hello", "world", "foo", "bar"]) == "string"

    def test_empty_returns_string(self) -> None:
        assert infer_type([]) == "string"

    def test_mixed_mostly_int(self) -> None:
        # 9/10 = 90% int — exceeds the 80% threshold → infer_type returns 'int'
        assert infer_type(["1", "2", "3", "4", "5", "6", "7", "8", "9", "hello"]) == "int"

    def test_mixed_below_threshold(self) -> None:
        # 5/10 = 50% int — below the 80% threshold → falls back to 'string'
        assert infer_type(["1", "2", "3", "4", "5", "a", "b", "c", "d", "e"]) == "string"


# ---------------------------------------------------------------------------
# matches_type
# ---------------------------------------------------------------------------
class TestMatchesType:
    def test_int_match(self) -> None:
        assert matches_type("42", "int") is True
        assert matches_type("abc", "int") is False

    def test_float_match(self) -> None:
        assert matches_type("3.14", "float") is True
        assert matches_type("abc", "float") is False

    def test_date_match(self) -> None:
        assert matches_type("2023-01-01", "date") is True
        assert matches_type("notadate", "date") is False

    def test_bool_match(self) -> None:
        assert matches_type("true", "bool") is True
        assert matches_type("yes", "bool") is True
        assert matches_type("maybe", "bool") is False

    def test_string_always_matches(self) -> None:
        assert matches_type("anything", "string") is True
        assert matches_type("12345", "string") is True


# ---------------------------------------------------------------------------
# analyze_csv (integration)
# ---------------------------------------------------------------------------
class TestAnalyzeCsv:
    def _write_csv(self, tmp_path: Path, content: str, name: str = "test.csv") -> str:
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_basic_analysis(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "name,age,city\nAlice,30,NYC\nBob,25,LA\n")
        report, rows = analyze_csv(path)
        assert report.total_rows == 2
        assert len(report.header) == 3
        assert report.delimiter == ","

    def test_duplicate_rows_detected(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "a,b\n1,2\n1,2\n3,4\n")
        report, rows = analyze_csv(path)
        assert len(report.duplicate_rows) > 0

    def test_empty_column_detected(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "a,b\n1,\n2,\n3,\n")
        report, rows = analyze_csv(path)
        assert "b" in report.empty_columns

    def test_duplicate_header_detected(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "a,a,b\n1,2,3\n")
        report, rows = analyze_csv(path)
        assert any("duplicate" in issue.lower() for issue in report.header_issues)

    def test_blank_header_detected(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "a,,b\n1,2,3\n")
        report, rows = analyze_csv(path)
        assert any("blank" in issue.lower() for issue in report.header_issues)


# ---------------------------------------------------------------------------
# clean_csv (integration)
# ---------------------------------------------------------------------------
class TestCleanCsv:
    def _write_csv(self, tmp_path: Path, content: str) -> str:
        path = tmp_path / "input.csv"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_drop_duplicates(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "a,b\n1,2\n1,2\n3,4\n")
        report, rows = analyze_csv(path)
        out = str(tmp_path / "out.csv")
        clean_csv(report, rows, out, drop_duplicates=True,
                  drop_empty_cols=False, strip_whitespace=False, normalize_nulls=False)
        with open(out, encoding="utf-8") as fh:
            reader = csv.reader(fh)
            data = list(reader)
        assert len(data) == 3  # header + 2 unique rows

    def test_strip_whitespace(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "a,b\n  hello  ,  world  \n")
        report, rows = analyze_csv(path)
        out = str(tmp_path / "out.csv")
        clean_csv(report, rows, out, drop_duplicates=False,
                  drop_empty_cols=False, strip_whitespace=True, normalize_nulls=False)
        with open(out, encoding="utf-8") as fh:
            reader = csv.reader(fh)
            rows_out = list(reader)
        assert rows_out[1][0] == "hello"
        assert rows_out[1][1] == "world"

    def test_normalize_nulls(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "a,b\n1,N/A\n2,null\n")
        report, rows = analyze_csv(path)
        out = str(tmp_path / "out.csv")
        clean_csv(report, rows, out, drop_duplicates=False,
                  drop_empty_cols=False, strip_whitespace=False, normalize_nulls=True)
        with open(out, encoding="utf-8") as fh:
            reader = csv.reader(fh)
            rows_out = list(reader)
        assert rows_out[1][1] == ""
        assert rows_out[2][1] == ""

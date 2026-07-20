# Mock pandas since it is not installed in the test environment
import io
import os
import sqlite3
import sys
from unittest.mock import MagicMock, patch

sys.modules["pandas"] = MagicMock()

# Add the path to tools/data-peek to sys.path so we can import from it
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_peek import (  # noqa: E402
    main,
    peek_csv_tsv,
    peek_json,
    peek_pandas_formats,
    peek_sqlite,
)


def test_peek_csv_tsv_success(capsys):
    content = "id,name,active,score\n1,Alice,True,95.5\n2,Bob,False,80\n3,,True,85\n"
    file_mock1 = io.StringIO(content)
    with patch("builtins.open", return_value=file_mock1):
        peek_csv_tsv("fake.csv", delimiter=",")
    captured = capsys.readouterr()
    assert "Format Sniffed: CSV" in captured.out
    assert "Row Count (excluding header): 3" in captured.out
    assert "Columns Count: 4" in captured.out
    assert "id" in captured.out
    assert "name" in captured.out
    assert "active" in captured.out
    assert "score" in captured.out


def test_peek_csv_tsv_empty(capsys):
    file_mock = io.StringIO("")
    with patch("builtins.open", return_value=file_mock):
        peek_csv_tsv("fake.csv", delimiter=",")
    captured = capsys.readouterr()
    assert "[-] Empty file." in captured.out


def test_peek_csv_tsv_error(capsys):
    with patch("builtins.open", side_effect=OSError("Disk error")):
        peek_csv_tsv("fake.csv", delimiter=",")
    captured = capsys.readouterr()
    assert "[-] Error reading file: Disk error" in captured.err


def test_peek_json_array(capsys):
    content = '[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]'
    file_mock = io.StringIO(content)
    with patch("builtins.open", return_value=file_mock):
        peek_json("fake.json")
    captured = capsys.readouterr()
    assert "Format Sniffed: JSON" in captured.out
    assert "Total Records: 2" in captured.out
    assert "id" in captured.out
    assert "name" in captured.out


def test_peek_jsonl(capsys):
    content = '{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}'
    file_mock = io.StringIO(content)
    with patch("builtins.open", return_value=file_mock):
        peek_json("fake.jsonl")
    captured = capsys.readouterr()
    assert "Format Sniffed: JSONL" in captured.out
    assert "Total Records: 2" in captured.out


def test_peek_json_empty(capsys):
    file_mock = io.StringIO("[]")
    with patch("builtins.open", return_value=file_mock):
        peek_json("fake.json")
    captured = capsys.readouterr()
    assert "Total Records: 0" in captured.out
    assert "[-] No records to inspect." in captured.out


def test_peek_json_error(capsys):
    with patch("builtins.open", side_effect=OSError("Read error")):
        peek_json("fake.json")
    captured = capsys.readouterr()
    assert "[-] Error parsing JSON: Read error" in captured.err


def test_peek_sqlite(capsys):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchall.side_effect = [
        [("users",)],
        [(0, "id", "INTEGER", 1, None, 1), (1, "name", "TEXT", 0, None, 0)],
    ]
    mock_cursor.fetchone.return_value = (42,)

    with patch("sqlite3.connect", return_value=mock_conn):
        peek_sqlite("fake.db")

    captured = capsys.readouterr()
    assert "Format Sniffed: SQLite Database" in captured.out
    assert "Tables Found (1): users" in captured.out
    assert "TABLE Schema: users" in captured.out
    assert "Row count: 42" in captured.out
    assert "id" in captured.out
    assert "INTEGER" in captured.out
    assert "name" in captured.out
    assert "TEXT" in captured.out


def test_peek_sqlite_error(capsys):
    with patch("sqlite3.connect", side_effect=sqlite3.Error("Connection timed out")):
        peek_sqlite("fake.db")
    captured = capsys.readouterr()
    assert "[-] SQLite connection error: Connection timed out" in captured.err


def test_peek_pandas_formats_no_pandas(capsys):
    with patch("data_peek.HAS_PANDAS", False):
        peek_pandas_formats("fake.xlsx", "Excel")
    captured = capsys.readouterr()
    assert "requires pandas" in captured.out


def test_peek_pandas_formats_excel(capsys):
    mock_series_name = MagicMock()
    mock_series_name.isnull().sum.return_value = 0
    mock_series_name.dropna.return_value.empty = False
    mock_series_name.dropna.return_value.iloc = ["Alice"]
    mock_series_name.dtype = "object"

    mock_series_age = MagicMock()
    mock_series_age.isnull().sum.return_value = 1
    mock_series_age.dropna.return_value.empty = False
    mock_series_age.dropna.return_value.iloc = [25]
    mock_series_age.dtype = "float64"

    mock_df = MagicMock()
    mock_df.columns = ["name", "age"]
    mock_df.__len__.return_value = 2

    def df_getitem(col):
        if col == "name":
            return mock_series_name
        if col == "age":
            return mock_series_age
        raise KeyError(col)

    mock_df.__getitem__.side_effect = df_getitem

    with patch("data_peek.HAS_PANDAS", True), patch(
        "pandas.read_excel", return_value=mock_df
    ):
        peek_pandas_formats("fake.xlsx", "Excel")

    captured = capsys.readouterr()
    assert "Format Sniffed: Excel (using Pandas parser)" in captured.out
    assert "Columns Count: 2" in captured.out
    assert "name" in captured.out
    assert "age" in captured.out
    assert "object" in captured.out
    assert "float64" in captured.out


def test_peek_pandas_formats_error(capsys):
    with patch("data_peek.HAS_PANDAS", True), patch(
        "pandas.read_parquet", side_effect=ValueError("Read failure")
    ):
        peek_pandas_formats("fake.parquet", "Parquet")
    captured = capsys.readouterr()
    assert "[-] Pandas read error: Read failure" in captured.err


def test_main_file_not_found(capsys):
    with patch("os.path.exists", return_value=False), patch(
        "sys.argv", ["data_peek.py", "missing.csv"]
    ):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1
    captured = capsys.readouterr()
    assert "Error: File not found" in captured.err


def test_main_routes():
    with patch("os.path.exists", return_value=True), patch(
        "os.path.getsize", return_value=123
    ), patch("data_peek.peek_csv_tsv") as mock_csv, patch(
        "sys.argv", ["data_peek.py", "file.csv"]
    ):
        main()
        mock_csv.assert_called_once_with(os.path.abspath("file.csv"), delimiter=",")

    with patch("os.path.exists", return_value=True), patch(
        "os.path.getsize", return_value=123
    ), patch("data_peek.peek_csv_tsv") as mock_tsv, patch(
        "sys.argv", ["data_peek.py", "file.tsv"]
    ):
        main()
        mock_tsv.assert_called_once_with(os.path.abspath("file.tsv"), delimiter="\t")

    with patch("os.path.exists", return_value=True), patch(
        "os.path.getsize", return_value=123
    ), patch("data_peek.peek_json") as mock_json, patch(
        "sys.argv", ["data_peek.py", "file.json"]
    ):
        main()
        mock_json.assert_called_once_with(os.path.abspath("file.json"))

    with patch("os.path.exists", return_value=True), patch(
        "os.path.getsize", return_value=123
    ), patch("data_peek.peek_sqlite") as mock_sqlite, patch(
        "sys.argv", ["data_peek.py", "file.sqlite3"]
    ):
        main()
        mock_sqlite.assert_called_once_with(os.path.abspath("file.sqlite3"))

    with patch("os.path.exists", return_value=True), patch(
        "os.path.getsize", return_value=123
    ), patch("data_peek.peek_pandas_formats") as mock_pandas, patch(
        "sys.argv", ["data_peek.py", "file.xlsx"]
    ):
        main()
        mock_pandas.assert_called_once_with(os.path.abspath("file.xlsx"), "Excel")

    with patch("os.path.exists", return_value=True), patch(
        "os.path.getsize", return_value=123
    ), patch("data_peek.peek_pandas_formats") as mock_pandas, patch(
        "sys.argv", ["data_peek.py", "file.parquet"]
    ):
        main()
        mock_pandas.assert_called_once_with(os.path.abspath("file.parquet"), "Parquet")

    mock_file = MagicMock()
    mock_file.read.return_value = b"SQLite format 3"
    mock_file.__enter__.return_value = mock_file

    with patch("os.path.exists", return_value=True), patch(
        "os.path.getsize", return_value=123
    ), patch("builtins.open", return_value=mock_file), patch(
        "data_peek.peek_sqlite"
    ) as mock_sqlite, patch(
        "sys.argv", ["data_peek.py", "file_no_ext"]
    ):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 0
    mock_sqlite.assert_called_once_with(os.path.abspath("file_no_ext"))


def test_main_fallback():
    mock_file = MagicMock()
    mock_file.read.return_value = b"some other header"
    mock_file.__enter__.return_value = mock_file

    with patch("os.path.exists", return_value=True), patch(
        "os.path.getsize", return_value=123
    ), patch("builtins.open", return_value=mock_file), patch(
        "data_peek.peek_csv_tsv"
    ) as mock_csv, patch(
        "sys.argv", ["data_peek.py", "file_no_ext"]
    ):
        main()
    mock_csv.assert_called_once_with(os.path.abspath("file_no_ext"))
